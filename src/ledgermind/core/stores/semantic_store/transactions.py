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
    Cross-platform file locking mechanism (using fcntl on Unix/Android).
    Thread-safe and process-safe.
    """
    _locks = {}
    _locks_mutex = threading.Lock()

    def __init__(self, lock_path: str, timeout: int = 60):
        self.lock_path = os.path.abspath(lock_path)
        self.timeout = timeout
        self._fd = None
        
        with self._locks_mutex:
            if self.lock_path not in self._locks:
                self._locks[self.lock_path] = threading.RLock()
            self._thread_lock = self._locks[self.lock_path]

    def acquire(self, exclusive: bool = True, timeout: Optional[int] = None):
        """
        Acquires lock to prevent concurrent modifications.
        Uses POSIX fcntl on Unix/Android for highly efficient, OS-level queuing.
        Falls back to atomic file creation (O_EXCL) on systems without fcntl.
        """
        effective_timeout = timeout if timeout is not None else self.timeout

        if not self._thread_lock.acquire(timeout=effective_timeout):
            raise TimeoutError(f"Could not acquire thread lock for {self.lock_path}")

        try:
            start_time = time.time()
            
            # Fast path: POSIX fcntl (Linux, Android, macOS)
            try:
                import fcntl
                flags = os.O_RDWR | os.O_CREAT
                
                # Open the file (creates it if it doesn't exist). 
                # We DO NOT use O_EXCL here because fcntl manages the lock state, not the file presence.
                if self._fd is None:
                    self._fd = os.open(self.lock_path, flags)
                
                op = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                
                # If timeout is 0, we use non-blocking mode immediately
                if timeout == 0:
                    try:
                        fcntl.flock(self._fd, op | fcntl.LOCK_NB)
                        return True
                    except (BlockingIOError, OSError):
                        return False
                
                # Blocking wait with a timeout mechanism
                while True:
                    try:
                        # Try to grab the lock non-blockingly first
                        fcntl.flock(self._fd, op | fcntl.LOCK_NB)
                        return True
                    except (BlockingIOError, OSError):
                        # Lock is held by someone else
                        if time.time() - start_time >= effective_timeout:
                            raise TimeoutError(f"Could not acquire fcntl lock on {self.lock_path} after {effective_timeout}s")
                        # Sleep briefly to avoid pegging CPU, then retry
                        time.sleep(0.01) # Short sleep for high performance

            except ImportError:
                # Fallback: Windows or environments without fcntl
                # We use a separate .lock file with O_EXCL for atomic creation
                semaphore_path = self.lock_path + ".lock"
                flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
                
                while True:
                    try:
                        # Atomic create
                        self._fd = os.open(semaphore_path, flags)
                        try:
                            os.write(self._fd, str(os.getpid()).encode())
                        except OSError:
                            pass
                        return True
                        
                    except FileExistsError:
                        # File exists -> check for stale lock
                        try:
                            with open(semaphore_path, 'r') as f:
                                pid_str = f.read().strip()
                            if pid_str:
                                pid = int(pid_str)
                                try:
                                    os.kill(pid, 0)
                                    # Process is alive, we just need to wait
                                except OSError:
                                    # Process is dead, remove stale lock and retry
                                    try: os.remove(semaphore_path)
                                    except OSError: pass
                                    continue
                        except (ValueError, OSError, IOError):
                            # Corrupted lock file, try to remove
                            try: os.remove(semaphore_path)
                            except OSError: pass
                            continue
                            
                        if time.time() - start_time >= effective_timeout:
                            if timeout == 0: return False
                            raise TimeoutError(f"Could not acquire file lock on {self.lock_path} after {effective_timeout}s")
                        
                        time.sleep(0.05)
                        
        except Exception:
            self._thread_lock.release()
            raise

    def release(self):
        try:
            if self._fd is not None:
                # If we have fcntl available, release the flock
                try:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                except (ImportError, OSError):
                    pass
                
                # Close the file descriptor
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None

            # Only remove the fallback .lock file.
            # CRITICAL: We DO NOT remove self.lock_path because that destroys the i-node 
            # and breaks fcntl queuing for other waiting processes.
            semaphore_path = self.lock_path + ".lock"
            if os.path.exists(semaphore_path):
                try:
                    os.remove(semaphore_path)
                except OSError:
                    pass
        finally:
            self._thread_lock.release()

class TransactionManager:
    """
    Implements ACID properties over a Git-backed file store.
    Uses WAL-like pattern via Backup/Restore and SQLite transaction.
    """
    def __init__(self, repo_path: str, meta_db: Any):
        self.repo_path = repo_path
        self.meta_db = meta_db
        self.lock = FileSystemLock(os.path.join(repo_path, ".lock"))
        self.backup_dir = os.path.join(repo_path, ".tx_backup")
        self._staged_files: List[str] = []

    @contextmanager
    def begin(self):
        """
        Starts a transaction.
        1. Acquires Exclusive Lock.
        2. Starts SQLite SAVEPOINT.
        3. Clears previous backup.
        """
        self.lock.acquire(exclusive=True)
        self._staged_files = []
        
        # Start DB transaction via SAVEPOINT
        db_conn = getattr(self.meta_db, '_conn', None)
        if db_conn:
            db_conn.execute("SAVEPOINT ledgermind_tx")

        # Ensure clean state but avoid redundant OS calls if directory is already empty
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
        elif os.listdir(self.backup_dir):
            for item in os.listdir(self.backup_dir):
                shutil.rmtree(os.path.join(self.backup_dir, item)) if os.path.isdir(os.path.join(self.backup_dir, item)) else os.remove(os.path.join(self.backup_dir, item))
        
        try:
            yield self
            self._commit()
            if db_conn:
                db_conn.execute("RELEASE ledgermind_tx")
        except Exception as e:
            logger.error(f"Transaction failed: {e}. Rolling back...")
            self._rollback()
            if db_conn:
                db_conn.execute("ROLLBACK TO ledgermind_tx")
            raise
        finally:
            if os.path.exists(self.backup_dir):
                shutil.rmtree(self.backup_dir)
            self.lock.release()

    def stage_file(self, relative_path: str):
        """
        Marks a file as part of the transaction. Backs it up if it exists.
        """
        full_path = os.path.join(self.repo_path, relative_path)
        backup_path = os.path.join(self.backup_dir, relative_path)
        
        if relative_path not in self._staged_files:
            if os.path.exists(full_path):
                # Copy original to backup
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(full_path, backup_path)
            self._staged_files.append(relative_path)

    def _rollback(self):
        """
        Restores files from backup and deletes new files created during transaction.
        """
        for rel_path in self._staged_files:
            full_path = os.path.join(self.repo_path, rel_path)
            backup_path = os.path.join(self.backup_dir, rel_path)
            
            if os.path.exists(backup_path):
                # Restore original
                shutil.copy2(backup_path, full_path)
            elif os.path.exists(full_path):
                # It was a new file, delete it
                os.remove(full_path)

    def _commit(self):
        """
        Finalizes the transaction. Verifies that all staged files are correctly written.
        The DB commit and Git commit are coordinated by the caller (SemanticStore).
        """
        for rel_path in self._staged_files:
            full_path = os.path.join(self.repo_path, rel_path)
            if not os.path.exists(full_path):
                raise RuntimeError(f"Atomic Commit Failed: File {rel_path} missing before commit.")
            
            # Additional check: ensure file is not empty if it's supposed to have data
            if os.path.getsize(full_path) == 0:
                logger.warning(f"File {rel_path} is empty during commit verification.")
