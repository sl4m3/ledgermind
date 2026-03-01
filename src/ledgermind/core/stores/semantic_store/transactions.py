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
        Acquires lock with atomic operations to prevent TOCTOU.

        Uses POSIX fcntl on Unix/Android with O_EXCL for atomicity.
        Falls back to file-based locking on other systems.

        Thread-safe and process-safe.
        """
        # ===== LAYER 1: Acquire thread lock first =====
        effective_timeout = timeout if timeout is not None else self.timeout

        if not self._thread_lock.acquire(timeout=effective_timeout):
            raise TimeoutError(f"Could not acquire thread lock for {self.lock_path}")

        lock_acquired = False

        try:
            # ===== LAYER 2: Setup file creation flags =====
            flags = os.O_RDWR | os.O_CREAT

            # CRITICAL: O_EXCL ensures atomic creation
            # If file exists, open() fails immediately (no race window)
            if exclusive:
                flags |= os.O_EXCL

            start_time = time.time()

            # ===== LAYER 3: Retry loop for lock contention =====
            while True:
                try:
                    # ATOMIC OPERATION: Open file (or fail if exists with O_EXCL)
                    # This single call creates the file AND acquires FD
                    # No race window between check and creation
                    self._fd = os.open(self.lock_path, flags)

                    # File is now open, we own the FD
                    # Write PID atomically AFTER we have the FD
                    try:
                        os.ftruncate(self._fd, 0)
                        os.write(self._fd, str(os.getpid()).encode())
                    except OSError:
                        pass

                except FileExistsError:
                    # File already exists -> lock is held by another process
                    # Check if it's stale lock (process died)
                    try:
                        with open(self.lock_path, 'r') as f:
                            pid_str = f.read().strip()

                        if pid_str:
                            try:
                                pid = int(pid_str)
                                # Check if process is still alive
                                os.kill(pid, 0)  # Signal 0 checks if alive

                                # Process is alive -> lock is valid
                                elapsed = time.time() - start_time

                                if elapsed >= effective_timeout:
                                    if timeout == 0:
                                        return False
                                    raise TimeoutError(
                                        f"Could not acquire lock on {self.lock_path} "
                                        f"after {effective_timeout}s (held by PID {pid})"
                                    )

                                # Wait before retrying
                                time.sleep(0.1)
                                continue

                            except (ValueError, OSError):
                                # Invalid PID or process check failed -> Treat as stale lock
                                pass

                        # Process is dead or invalid PID -> stale lock -> Remove and retry
                        try:
                            os.remove(self.lock_path)
                        except OSError:
                            pass
                        continue

                    except (OSError, IOError):
                        # Error reading/stale check -> just wait and retry
                        elapsed = time.time() - start_time

                        if elapsed >= effective_timeout:
                            if timeout == 0:
                                return False
                            raise TimeoutError(
                                f"Could not acquire lock on {self.lock_path} "
                                f"after {effective_timeout}s"
                            )

                        time.sleep(0.1)
                        continue

                # ===== LAYER 4: Apply fcntl lock (Unix/Linux/Android) =====
                try:
                    import fcntl

                    op = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH

                    # Try non-blocking first
                    try:
                        # FD is already open, now apply fcntl lock
                        fcntl.flock(self._fd, op | fcntl.LOCK_NB)
                        lock_acquired = True
                        return True

                    except (BlockingIOError, OSError) as e:
                        import errno

                        # Check if it's just blocked (expected for contention)
                        if isinstance(e, BlockingIOError) or e.errno in (errno.EAGAIN, errno.EACCES):
                            # Lock is held by another process via fcntl
                            elapsed = time.time() - start_time

                            if elapsed >= effective_timeout:
                                if timeout == 0:
                                    try: os.close(self._fd)
                                    except OSError: pass
                                    self._fd = None
                                    return False

                                raise TimeoutError(
                                    f"Could not acquire fcntl lock on {self.lock_path} "
                                    f"after {effective_timeout}s"
                                )

                            # Wait and retry
                            time.sleep(0.1)
                            try: os.close(self._fd)
                            except OSError: pass
                            self._fd = None
                            continue

                        # Other error
                        raise

                except ImportError:
                    # fcntl not available -> We rely on O_EXCL
                    lock_acquired = True
                    return True

                except Exception as e:
                    logger.error(f"Unexpected error in fcntl lock: {e}")
                    raise RuntimeError(f"Lock acquisition failed: {e}")

        except TimeoutError:
            raise

        except Exception:
            self._thread_lock.release()
            raise

        finally:
            if not lock_acquired:
                self._thread_lock.release()

    def release(self):
        try:
            if self._fd:
                try:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                except (ImportError, OSError): pass
                
                try:
                    os.close(self._fd)
                except OSError: pass
                self._fd = None
                
            # Clean up all lock files to prevent O_EXCL false positives for next acquirer
            for path in [self.lock_path, self.lock_path + ".lock"]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError: pass
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
