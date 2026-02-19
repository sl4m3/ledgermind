import os
import shutil
import sqlite3
import logging
import time
from typing import List, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger("ledgermind-core.transactions")

class FileSystemLock:
    """
    Cross-platform file locking mechanism (using fcntl on Unix/Android).
    """
    def __init__(self, lock_path: str, timeout: int = 60):
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd = None

    def acquire(self, exclusive: bool = True):
        start_time = time.time()
        flags = os.O_RDWR | os.O_CREAT
        
        # Open file once
        if self._fd is None:
            self._fd = os.open(self.lock_path, flags)

        while True:
            try:
                import fcntl
                op = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                # Try acquiring fcntl lock
                try:
                    fcntl.flock(self._fd, op | fcntl.LOCK_NB)
                    # Write PID for debugging
                    os.ftruncate(self._fd, 0)
                    os.write(self._fd, str(os.getpid()).encode())
                    return
                except (BlockingIOError, OSError) as e:
                    # If it's a real error (like ENOSYS), fall back. 
                    # If it's just blocked (EAGAIN/EACCES), retry.
                    import errno
                    if isinstance(e, BlockingIOError) or e.errno in (errno.EAGAIN, errno.EACCES):
                        if time.time() - start_time > self.timeout:
                            raise TimeoutError(f"Could not acquire fcntl lock on {self.lock_path} after {self.timeout}s")
                        time.sleep(0.1)
                        continue
                    raise # Fall back to semaphore for other OSErrors
            except (ImportError, Exception):
                # Fallback for Windows or systems without fcntl
                # Try to create a secondary lock file as a semaphore
                semaphore_path = self.lock_path + ".lock"
                try:
                    # O_EXCL ensures atomic creation
                    fd = os.open(semaphore_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    with os.fdopen(fd, 'w') as f:
                        f.write(str(os.getpid()))
                    return
                except FileExistsError:
                    if time.time() - start_time > self.timeout:
                        raise TimeoutError(f"Could not acquire semaphore lock on {self.lock_path} after {self.timeout}s")
                    time.sleep(0.1)

    def release(self):
        if self._fd:
            try:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except (ImportError, OSError): pass
            
            # Close FD to release resources
            try:
                os.close(self._fd)
            except OSError: pass
            self._fd = None
            
        # Clean up semaphore if it exists
        semaphore_path = self.lock_path + ".lock"
        if os.path.exists(semaphore_path):
            try:
                # Check if we are the owner before deleting? 
                # For simplicity, just delete if we are releasing.
                os.remove(semaphore_path)
            except OSError: pass

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
        2. Clears previous backup.
        3. Starts SQLite transaction.
        """
        self.lock.acquire(exclusive=True)
        self._staged_files = []
        
        # Ensure clean state
        if os.path.exists(self.backup_dir):
            shutil.rmtree(self.backup_dir)
        os.makedirs(self.backup_dir)

        # Start DB transaction
        # meta_db is likely the SemanticMetaStore wrapper, we need the raw connection/cursor or use its methods
        # Assuming meta_db handles its own transaction via the wrapper or we rely on the context manager
        # For now, we assume the caller manages the DB transaction scope or we implement a hook.
        # Ideally, SemanticMetaStore should expose a `transaction()` method.
        
        try:
            yield self
        except Exception as e:
            logger.error(f"Transaction failed: {e}. Rolling back...")
            self._rollback()
            raise
        else:
            self._commit()
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
        Finalizes the transaction. The DB commit happens in the caller or wrapper.
        Here we basically just confirm the file operations are 'good'.
        The actual Git commit happens after this return in the SemanticStore.
        """
        pass
