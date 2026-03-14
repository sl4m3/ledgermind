import os
import shutil
import sqlite3
import logging
import time
import threading
from typing import List, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger("ledgermind-core.transactions")

class FileSystemLock:
    """
    Robust OS-level file locking mechanism using fcntl.flock on Unix/Android.
    Ensures that only one process or thread can modify the store at a time.
    
    CRITICAL: File descriptor (_fd) is shared across all instances for the same path
    to ensure proper locking even when multiple Memory() instances access same storage.
    """
    _global_thread_locks = {}
    _global_file_descriptors = {}  # Shared FD for same path
    _global_fd_ref_counts = {}  # Reference count for shared FD
    _registry_lock = threading.Lock()

    def __init__(self, lock_path: str, timeout: int = 180):
        self.lock_path = os.path.abspath(lock_path)
        self.timeout = timeout
        self._local = threading.local()

        # Ensure we use the same RLock and FD for the same path across all instances
        with self._registry_lock:
            if self.lock_path not in self._global_thread_locks:
                self._global_thread_locks[self.lock_path] = threading.RLock()
                self._global_file_descriptors[self.lock_path] = None
                self._global_fd_ref_counts[self.lock_path] = 0
        self._thread_lock = self._global_thread_locks[self.lock_path]

    @property
    def _lock_depth(self) -> int:
        """Track recursive locking depth for the current thread."""
        return getattr(self._local, 'depth', 0)

    @_lock_depth.setter
    def _lock_depth(self, value: int):
        self._local.depth = value

    @property
    def _fd(self) -> Optional[int]:
        """Shared file descriptor for this lock path."""
        return self._global_file_descriptors.get(self.lock_path)

    @_fd.setter
    def _fd(self, value: Optional[int]):
        self._global_file_descriptors[self.lock_path] = value

    def acquire(self, exclusive: bool = True, timeout: Optional[int] = None):
        """
        Acquires an OS-level lock. Supports recursion within the same thread.
        Uses shared file descriptor with reference counting.
        """
        # 1. Thread-level isolation first
        self._thread_lock.acquire()

        # Handle recursive locking
        if self._lock_depth > 0:
            self._lock_depth += 1
            return True

        effective_timeout = timeout if timeout is not None else self.timeout
        start_time = time.time()

        try:
            import fcntl
            flags = os.O_RDWR | os.O_CREAT

            # Open shared FD if needed (with ref count)
            with self._registry_lock:
                if self._fd is None:
                    self._fd = os.open(self.lock_path, flags)
                    self._global_fd_ref_counts[self.lock_path] = 1
                else:
                    self._global_fd_ref_counts[self.lock_path] += 1

            op = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH

            # Try non-blocking first for immediate access
            try:
                fcntl.flock(self._fd, op | fcntl.LOCK_NB)
                self._lock_depth = 1
                return True
            except (BlockingIOError, OSError):
                if timeout == 0:
                    self._thread_lock.release()
                    return False

            # Blocking wait with timeout
            while True:
                try:
                    # Retry non-blocking to allow timeout control
                    fcntl.flock(self._fd, op | fcntl.LOCK_NB)
                    self._lock_depth = 1
                    return True
                except (BlockingIOError, OSError):
                    if time.time() - start_time >= effective_timeout:
                        self._thread_lock.release()
                        raise TimeoutError(f"Could not acquire OS lock on {self.lock_path} after {effective_timeout}s.")
                    time.sleep(0.05)

        except Exception as e:
            self._thread_lock.release()
            if isinstance(e, ImportError):
                # Fallback for Windows
                self._lock_depth = 1
                return True
            raise

    def release(self):
        """Releases the lock with reference counting for shared FD."""
        try:
            if self._lock_depth > 1:
                self._lock_depth -= 1
                return

            # Only close FD if we're the last user
            with self._registry_lock:
                if self._fd is not None:
                    self._global_fd_ref_counts[self.lock_path] -= 1
                    if self._global_fd_ref_counts[self.lock_path] <= 0:
                        try:
                            import fcntl
                            fcntl.flock(self._fd, fcntl.LOCK_UN)
                            os.close(self._fd)
                        except Exception:
                            pass
                        finally:
                            self._fd = None
                            self._global_fd_ref_counts[self.lock_path] = 0
                    self._lock_depth = 0
        finally:
            self._thread_lock.release()

class TransactionManager:
    """
    Implements ACID properties over a Git-backed file store.
    
    CRITICAL: Uses singleton pattern per repo_path to ensure all Memory() instances
    accessing the same storage share the same lock. The lock is shared but each
    transaction uses its own meta_db connection.
    """
    _locks = {}  # Shared locks per repo_path
    _registry_lock = threading.Lock()
    
    def __init__(self, repo_path: str, meta_db: Any):
        self.repo_path = os.path.abspath(repo_path)
        self.meta_db = meta_db  # Each instance has its own meta_db
        # Get or create shared lock for this path
        with self._registry_lock:
            if self.repo_path not in self._locks:
                self._locks[self.repo_path] = FileSystemLock(os.path.join(self.repo_path, ".lock"))
        self.lock = self._locks[self.repo_path]
        self.backup_dir = os.path.join(self.repo_path, ".tx_backup")
        self._staged_files: List[str] = []

    @contextmanager
    def begin(self):
        import uuid
        self._staged_files = []
        
        # 1. Acquire OS Lock (Wait up to 60s)
        # This prevents other processes from starting their own transactions
        self.lock.acquire(exclusive=True)
        
        db_conn = getattr(self.meta_db, '_conn', None)
        try:
            # 2. Start EXCLUSIVE DB transaction with retries
            if db_conn:
                max_retries = 15
                retry_delay = 0.1
                for attempt in range(max_retries):
                    try:
                        db_conn.execute("BEGIN IMMEDIATE")
                        break
                    except sqlite3.OperationalError as e:
                        if "within a transaction" in str(e):
                            break # Already in transaction
                        if "locked" in str(e) and attempt < max_retries - 1:
                            time.sleep(retry_delay * (1.5 ** attempt))
                            continue
                        raise

            # 3. Prepare backup directory
            if not os.path.exists(self.backup_dir):
                os.makedirs(self.backup_dir)
            
            yield self
            
            # 4. Verify all staged files exist before final commit
            self._commit()
            
            # 5. Final DB Commit
            if db_conn:
                db_conn.execute("COMMIT")
                
        except Exception as e:
            logger.error(f"Transaction failed: {e}. Rolling back...")
            # 1. Rollback DB first
            if db_conn:
                try:
                    db_conn.execute("ROLLBACK")
                except Exception: pass
            
            # 2. Rollback files on disk
            self._rollback()
            raise
        finally:
            if os.path.exists(self.backup_dir):
                try: shutil.rmtree(self.backup_dir)
                except: pass
            # 6. Release OS Lock
            self.lock.release()

    def stage_file(self, relative_path: str):
        full_path = os.path.join(self.repo_path, relative_path)
        backup_path = os.path.join(self.backup_dir, relative_path)
        if relative_path not in self._staged_files:
            if os.path.exists(full_path):
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(full_path, backup_path)
            self._staged_files.append(relative_path)

    def _rollback(self):
        for rel_path in self._staged_files:
            full_path = os.path.join(self.repo_path, rel_path)
            backup_path = os.path.join(self.backup_dir, rel_path)
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, full_path)
            elif os.path.exists(full_path):
                os.remove(full_path)

    def _commit(self):
        for rel_path in self._staged_files:
            full_path = os.path.join(self.repo_path, rel_path)
            if not os.path.exists(full_path):
                raise RuntimeError(f"Atomic Commit Failed: File {rel_path} missing.")
