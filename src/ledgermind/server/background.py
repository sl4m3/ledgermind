import logging
import time
import os
import threading
import subprocess
import argparse
import sys
import signal
import atexit
from typing import Optional, Dict, List, Any
from datetime import datetime

# Add the 'src' directory to sys.path to ensure imports work regardless of CWD
# This makes the script location-independent
script_dir = os.path.dirname(os.path.abspath(__file__))
# Correct root discovery: background.py is in src/ledgermind/server/
project_root = os.path.abspath(os.path.join(script_dir, "../../../"))
src_root = os.path.abspath(os.path.join(script_dir, "../../"))

if src_root not in sys.path:
    sys.path.insert(0, src_root)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from ledgermind.core.api.memory import Memory
except ImportError:
    # Fallback for weird path cases
    sys.path.insert(0, os.getcwd() + "/src")
    from ledgermind.core.api.memory import Memory

logger = logging.getLogger("ledgermind.worker")

class BackgroundWorker:
    """
    Active Runtime Loop ("The Heartbeat") for LedgerMind.
    Designed to run as a standalone, detached process.
    """
    def __init__(self, memory: Memory, interval_seconds: int = 300, log_path: Optional[str] = None):
        self.memory = memory
        # Ensure storage path is absolute for reliability
        self.memory.storage_path = os.path.abspath(self.memory.storage_path)

        self.interval = interval_seconds
        self.enrichment_interval = 60

        # Setup logging only if a path is provided, otherwise assume external setup
        if log_path:
            self._setup_logging(os.path.abspath(log_path))

        self.running = False
        self._stop_event = threading.Event()
        self.maintenance_thread: Optional[threading.Thread] = None
        self.enrichment_thread: Optional[threading.Thread] = None

        self.last_run: Dict[str, datetime] = {}
        self.status = "stopped"
        self.errors: List[str] = []
        self._active_subprocesses: List[Any] = []
        self._proc_lock = threading.Lock()
        self._worker_lock_fd = None
        self._signal_received = False
        self._setup_signal_handlers()
        atexit.register(self._cleanup_on_exit)

    def _setup_logging(self, log_path: str):
        """Initializes standalone logging for the worker process."""
        log_dir = os.path.dirname(log_path)
        if log_dir: os.makedirs(log_dir, exist_ok=True)

        # Clear existing handlers to avoid duplicates
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        fh = logging.FileHandler(log_path, mode='w')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(fh)
        root_logger.setLevel(logging.INFO)
        logger.info(f"Worker logging initialized at {log_path}")

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        if threading.current_thread() is not threading.main_thread():
            return

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self._signal_received = True
            self._stop_event.set()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)

    def _cleanup_on_exit(self):
        """Cleanup called by atexit."""
        if self.running:
            logger.warning("Worker still running at exit, forcing cleanup...")
            self._cleanup_orphans()

    def start(self):
        """Starts the background worker with single-instance enforcement."""
        if self.running:
            logger.warning("Worker is already running")
            return
        self._cleanup_orphans()

        if not self._acquire_worker_lock():
            # If we can't get the lock, another worker is already active
            logger.info("Exiting: another Background Worker is already running for this storage path.")
            sys.exit(0)

        logger.info(f"Worker lock acquired (PID: {os.getpid()}, storage: {self.memory.storage_path})")
        self.running = True
        self._stop_event.clear()
        self.status = "running"

        self.maintenance_thread = threading.Thread(target=self._maintenance_loop, name="MaintWorker", daemon=True)
        self.maintenance_thread.start()

        self.enrichment_thread = threading.Thread(target=self._enrichment_loop, name="EnrichWorker", daemon=True)
        self.enrichment_thread.start()

        logger.info("Background Worker started.")

    def _cleanup_orphans(self):
        """Cleans up orphan gemini processes belonging to this worker instance."""
        try:
            # Kill gemini processes with empty extensions (used by enricher)
            subprocess.run(
                "pkill -f 'gemini --extensions \"\" -m'",
                shell=True,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
        except Exception:
            pass

    def stop(self, timeout: float = 10.0):
        """Gracefully shuts down the worker and all subprocesses."""
        if not self.running:
            return
        self.running = False
        self._stop_event.set()

        # 1. Terminate all registered enricher subprocesses
        with self._proc_lock:
            logger.info(f"Terminating {len(self._active_subprocesses)} active subprocesses...")
            for proc in self._active_subprocesses:
                try:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=1.0)
                        except Exception:
                            proc.kill()
                except Exception as e:
                    logger.warning(f"Failed to terminate subprocess: {e}")
            self._active_subprocesses.clear()

        # 2. Wait for threads to finish
        if self.maintenance_thread:
            self.maintenance_thread.join(timeout=timeout/2)
            if self.maintenance_thread.is_alive():
                logger.warning("Maintenance thread did not stop gracefully")
        if self.enrichment_thread:
            self.enrichment_thread.join(timeout=timeout/2)
            if self.enrichment_thread.is_alive():
                logger.warning("Enrichment thread did not stop gracefully")

        self.status = "stopped"
        self._release_worker_lock()

        # 3. Final cleanup of orphan gemini processes (safety net)
        self._cleanup_orphans()

        logger.info("Background Worker stopped.")

    def register_process(self, proc: Any):
        with self._proc_lock: self._active_subprocesses.append(proc)

    def unregister_process(self, proc: Any):
        with self._proc_lock:
            if proc in self._active_subprocesses: self._active_subprocesses.remove(proc)

    def _acquire_worker_lock(self) -> bool:
        """Acquires exclusive lock to ensure only one worker runs per storage path.
        Returns True if lock acquired, False if another worker is already running."""
        import fcntl

        # PID file is always in the storage path
        pid_file = os.path.join(self.memory.storage_path, "worker.pid")

        # First, check if a stale lock file exists from a dead process
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        existing_pid = int(content)
                        # Check if process is still running
                        if not self._is_process_running(existing_pid):
                            logger.warning(f"Removing stale lock file from dead process (PID: {existing_pid})")
                            os.remove(pid_file)
            except (ValueError, IOError):
                # Corrupted lock file, remove it
                if os.path.exists(pid_file):
                    logger.warning("Removing corrupted lock file")
                    os.remove(pid_file)

        try:
            # Fix: Open in 'a+' mode to avoid truncation before lock
            self._worker_lock_fd = open(pid_file, 'a+')
            fcntl.flock(self._worker_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Now that we have the lock, truncate and write our PID
            self._worker_lock_fd.seek(0)
            self._worker_lock_fd.truncate()
            self._worker_lock_fd.write(str(os.getpid()))
            self._worker_lock_fd.flush()
            return True
        except (IOError, OSError):
            if self._worker_lock_fd:
                try:
                    self._worker_lock_fd.close()
                except Exception: pass
                self._worker_lock_fd = None
            
            # Try to read PID for better error message
            existing_pid = ""
            try:
                if os.path.exists(pid_file):
                    with open(pid_file, 'r') as f:
                        existing_pid = f.read().strip()
            except Exception:
                pass
            
            if existing_pid:
                logger.error(f"Another worker is already running (PID: {existing_pid}). Storage path: {self.memory.storage_path}")
            else:
                logger.error(f"Another worker is already running. Storage path: {self.memory.storage_path}")
            return False

    @staticmethod
    def _is_process_running(pid: int) -> bool:
        """
        Check if a process with given PID is still running and not a zombie.
        On Unix, we check /proc/PID/status for 'State: Z (zombie)'.
        """
        try:
            # 1. Basic signal check
            os.kill(pid, 0)
            
            # 2. Deep check for Zombie state (Unix only)
            status_path = f"/proc/{pid}/status"
            if os.path.exists(status_path):
                try:
                    with open(status_path, 'r') as f:
                        for line in f:
                            if line.startswith("State:"):
                                if "Z (zombie)" in line:
                                    logger.warning(f"Detected zombie process (PID: {pid}). Treating as dead.")
                                    return False
                                break
                except Exception: 
                    # If we can't read /proc (unlikely on Termux), 
                    # fallback to True since kill(0) succeeded
                    pass
                
            return True
        except OSError:
            return False

    def _release_worker_lock(self):
        import fcntl
        if self._worker_lock_fd:
            try:
                fcntl.flock(self._worker_lock_fd, fcntl.LOCK_UN)
                self._worker_lock_fd.close()
                pid_file = os.path.join(self.memory.storage_path, "worker.pid")
                if os.path.exists(pid_file): os.remove(pid_file)
            except Exception: pass
            finally: self._worker_lock_fd = None

    def _maintenance_loop(self):
        self._stop_event.wait(2.0)
        while self.running:
            try:
                start_time = time.time()
                self._run_health_check()
                self._run_git_sync()
                self._run_maintenance()
                elapsed = time.time() - start_time
                if self._stop_event.wait(max(1.0, self.interval - elapsed)): break
            except Exception as e:
                logger.error(f"Maintenance Loop crashed: {e}")
                if self._stop_event.wait(60.0): break

    def _enrichment_loop(self):
        self._stop_event.wait(15.0)
        while self.running:
            try:
                start_time = time.time()
                # SQLite is thread-safe with check_same_thread=False
                arbitration_mode = self.memory.semantic.meta.get_config("arbitration_mode", "lite")
                
                if arbitration_mode != "lite":
                    from ledgermind.core.reasoning.llm_enrichment import LLMEnricher
                    enricher = LLMEnricher(mode=arbitration_mode, worker=self)
                    try:
                        logger.info(f"Starting Enrichment Cycle ({arbitration_mode})...")
                        enricher.process_batch(self.memory)
                        self.last_run["enrichment"] = datetime.now()
                    finally:
                        enricher.close()
                
                elapsed = time.time() - start_time
                if self._stop_event.wait(max(5.0, self.enrichment_interval - elapsed)): break
            except Exception as e:
                logger.error(f"Enrichment Loop crashed: {e}")
                if self._stop_event.wait(120.0): break

    def _run_health_check(self):
        try:
            self.memory.check_environment()
            # Stale lock cleaning logic is now handled by OS-level fcntl
            self.last_run["health"] = datetime.now()
        except Exception as e: logger.error(f"Health check failed: {e}")

    def _run_git_sync(self):
        try:
            if self.memory._git_available:
                self.memory.sync_git(repo_path=".", limit=5)
                self.last_run["git_sync"] = datetime.now()
        except Exception as e: logger.warning(f"Git sync failed: {e}")

    def _run_maintenance(self):
        try:
            self.memory.run_maintenance()
            self.last_run["maintenance"] = datetime.now()
        except Exception as e: logger.error(f"Maintenance failed: {e}")

    def run_forever(self):
        """Main worker loop with session registration monitor."""
        self.start()
        
        session_dir = os.path.join(self.memory.storage_path, "sessions")
        os.makedirs(session_dir, exist_ok=True)
        
        try:
            while self.running:
                # 1. Scan sessions/ for active PIDs or any generic lock files
                active_sessions = 0
                try:
                    for filename in os.listdir(session_dir):
                        if not filename.endswith(".lock"): continue
                        
                        file_path = os.path.join(session_dir, filename)
                        try:
                            # Try to treat filename as PID for deep verification
                            pid_str = filename.split(".")[0]
                            if pid_str.isdigit():
                                pid = int(pid_str)
                                # Only clean up if we are SURE the process is dead
                                if self._is_process_running(pid):
                                    active_sessions += 1
                                else:
                                    # Clean up stale session file
                                    try: os.remove(file_path)
                                    except: pass
                            else:
                                # Generic lock file (e.g. server.lock), assume active
                                active_sessions += 1
                        except Exception:
                            # In case of any error parsing/checking, be safe and assume active
                            active_sessions += 1
                except OSError:
                    # Dir might be temporarily unavailable
                    active_sessions = 1 # Assume someone is active to be safe
                
                # 2. If no active sessions remain, initiate shutdown
                if active_sessions == 0:
                    logger.info("No active sessions detected. Shutting down worker.")
                    break

                if self._stop_event.wait(5.0): # Check sessions every 5s
                    break
                if self._signal_received:
                    break
        except (KeyboardInterrupt, SystemExit):
            logger.info("Interrupt received, initiating shutdown...")
        finally:
            self.stop()

if __name__ == "__main__":
    from ledgermind.core.core.schemas import TrustBoundary

    parser = argparse.ArgumentParser(description="LedgerMind Standalone Worker")
    parser.add_argument("--storage", required=True, help="Absolute path to storage")
    parser.add_argument("--log", help="Absolute path to log file")
    args = parser.parse_args()

    # Create memory instance with absolute path
    storage_abs = os.path.abspath(args.storage)
    memory = Memory(storage_path=storage_abs, trust_boundary=TrustBoundary.AGENT_WITH_INTENT)
    
    # Initialize worker with absolute log path
    log_abs = os.path.abspath(args.log) if args.log else None
    worker = BackgroundWorker(memory, log_path=log_abs)
    
    worker.run_forever()
