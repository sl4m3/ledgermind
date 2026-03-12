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
script_dir = os.path.dirname(os.path.abspath(__file__))
src_root = os.path.abspath(os.path.join(script_dir, "../../"))
if src_root not in sys.path:
    sys.path.insert(0, src_root)

try:
    from ledgermind.core.api.memory import Memory
except ImportError:
    sys.path.insert(0, os.getcwd() + "/src")
    from ledgermind.core.api.memory import Memory

logger = logging.getLogger("ledgermind.worker")

class BackgroundWorker:
    """
    Active Runtime Loop ("The Heartbeat") for LedgerMind.
    Designed to run as a standalone, detached process.
    Supports graceful shutdown and lock file monitoring.
    """
    def __init__(self, memory: Memory, interval_seconds: int = 300, log_path: Optional[str] = None):
        self.memory = memory
        self.memory.storage_path = os.path.abspath(self.memory.storage_path)

        self.interval = interval_seconds
        self.enrichment_interval = 60

        if log_path:
            self._setup_logging(os.path.abspath(log_path))

        self.running = False
        self._stop_event = threading.Event()
        self.enrichment_thread: Optional[threading.Thread] = None
        self.watchdog_thread: Optional[threading.Thread] = None

        self.last_run: Dict[str, datetime] = {}
        self.status = "stopped"
        self._active_subprocesses: List[Any] = []
        self._proc_lock = threading.Lock()
        self._worker_lock_fd = None
        self._signal_received = False
        self._setup_signal_handlers()
        atexit.register(self._cleanup_on_exit)

    def _setup_logging(self, log_path: str):
        log_dir = os.path.dirname(log_path)
        if log_dir: os.makedirs(log_dir, exist_ok=True)
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        fh = logging.FileHandler(log_path, mode='w')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(fh)
        root_logger.setLevel(logging.INFO)
        logger.info(f"Worker logging initialized at {log_path}")

    def _setup_signal_handlers(self):
        """Setup signal handlers for immediate forced shutdown."""
        if threading.current_thread() is not threading.main_thread():
            return

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating immediate forced shutdown...")
            self._signal_received = True
            self.running = False
            self.stop()
            # Hard exit to break any blocking native calls in main thread
            os._exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        if hasattr(signal, 'SIGPIPE'):
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)

    def _cleanup_on_exit(self):
        if self.running:
            self.stop()

    def start(self):
        if self.running: return
        self._cleanup_orphans()
        if not self._acquire_worker_lock():
            logger.info("Exiting: another Background Worker is already running.")
            sys.exit(0)

        logger.info(f"Worker lock acquired (PID: {os.getpid()}, storage: {self.memory.storage_path})")
        self.running = True
        self._stop_event.clear()
        self.status = "running"

        # 1. Start enrichment thread
        self.enrichment_thread = threading.Thread(target=self._enrichment_loop, name="EnrichWorker", daemon=True)
        self.enrichment_thread.start()
        
        # 2. Start watchdog thread (10s interval)
        self.watchdog_thread = threading.Thread(target=self._lock_watchdog, name="WorkerWatchdog", daemon=True)
        self.watchdog_thread.start()
        
        logger.info("Background Worker started (Maintenance: MainThread, Enrichment: Parallel, Watchdog: 10s).")

    def _lock_watchdog(self):
        """Monitor worker.pid file. If missing, force immediate exit."""
        lock_path = os.path.join(self.memory.storage_path, "worker.pid")
        while self.running:
            if not os.path.exists(lock_path):
                logger.warning("Worker lock file (worker.pid) disappeared. Forcing immediate shutdown.")
                self.stop()
                os._exit(0)
            
            # Sleep 10s but check running flag every 1s
            for _ in range(10):
                if not self.running: return
                time.sleep(1.0)

    def stop(self, timeout: float = 5.0):
        """Gracefully but rapidly shuts down the worker and kills all subprocesses."""
        self.running = False
        self._stop_event.set()
        self.status = "stopping"

        # 1. Kill all registered gemini subprocesses immediately
        with self._proc_lock:
            if self._active_subprocesses:
                logger.info(f"Killing {len(self._active_subprocesses)} active subprocesses...")
                for proc in self._active_subprocesses:
                    try:
                        if proc.poll() is None:
                            proc.kill() # Direct kill for speed
                    except Exception: pass
                self._active_subprocesses.clear()

        # 2. Release lock and remove worker.pid
        self._release_worker_lock()
        self.status = "stopped"
        logger.info("Background Worker stopped.")

    def register_process(self, proc: Any):
        with self._proc_lock: self._active_subprocesses.append(proc)

    def unregister_process(self, proc: Any):
        with self._proc_lock:
            if proc in self._active_subprocesses: self._active_subprocesses.remove(proc)

    def _acquire_worker_lock(self) -> bool:
        import fcntl
        pid_file = os.path.join(self.memory.storage_path, "worker.pid")
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    content = f.read().strip()
                    if content and not self._is_process_running(int(content)):
                        os.remove(pid_file)
            except Exception: pass

        try:
            self._worker_lock_fd = open(pid_file, 'a+')
            fcntl.flock(self._worker_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._worker_lock_fd.seek(0)
            self._worker_lock_fd.truncate()
            self._worker_lock_fd.write(str(os.getpid()))
            self._worker_lock_fd.flush()
            return True
        except Exception:
            if self._worker_lock_fd: self._worker_lock_fd.close()
            return False

    @staticmethod
    def _is_process_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError: return False

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

    def _enrichment_loop(self):
        self._stop_event.wait(10.0)
        while self.running:
            try:
                start_time = time.time()
                mode = self.memory.semantic.meta.get_config("arbitration_mode", "optimal")
                if mode != "lite":
                    from ledgermind.core.reasoning.llm_enrichment import LLMEnricher
                    enricher = LLMEnricher(mode=mode, worker=self)
                    try:
                        enricher.process_batch(self.memory)
                    finally: enricher.close()
                
                # Responsive sleep
                elapsed = time.time() - start_time
                wait_time = max(5.0, self.enrichment_interval - elapsed)
                for _ in range(int(wait_time * 2)):
                    if not self.running: break
                    time.sleep(0.5)
            except Exception as e:
                logger.error(f"Enrichment Loop error: {e}")
                if self._stop_event.wait(30.0): break

    def run_forever(self):
        """Main worker loop with lock monitoring and maintenance."""
        try:
            self.start()
            session_dir = os.path.join(self.memory.storage_path, "sessions")
            lock_path = os.path.join(self.memory.storage_path, "worker.pid")
            os.makedirs(session_dir, exist_ok=True)
            
            last_maintenance = 0
            
            while self.running:
                # 0. CRITICAL: Lock file health check (Manual removal detection)
                if not os.path.exists(lock_path):
                    logger.warning("Worker lock file (worker.pid) deleted manually. Shutting down.")
                    break

                now = time.time()
                # 1. MAINTENANCE CYCLE
                if now - last_maintenance >= self.interval:
                    try:
                        logger.info("Starting maintenance cycle in main thread...")
                        self.memory.check_environment()
                        self.memory.run_maintenance(stop_event=self._stop_event)
                        last_maintenance = time.time()
                    except Exception as me:
                        logger.error(f"Maintenance failed: {me}")

                # 2. SESSION MONITORING & RESPONSIVE SLEEP
                # Check sessions and flags every 5 seconds
                for _ in range(20): # ~100 seconds total max sleep between checks
                    if not self.running or not os.path.exists(lock_path): break
                    
                    # Check active client sessions
                    active = 0
                    try:
                        for f in os.listdir(session_dir):
                            if f.endswith(".lock") and self._is_process_running(int(f.split(".")[0])):
                                active += 1
                    except Exception: active = 1
                    
                    if active == 0:
                        logger.info("No active sessions. Shutting down.")
                        self.running = False
                        break
                    
                    if self._stop_event.wait(5.0): break
                        
        except Exception as fatal_e:
            logger.critical(f"FATAL: Worker loop crashed: {fatal_e}", exc_info=True)
        finally:
            self.stop()

    def _cleanup_orphans(self):
        try:
            import shutil
            pkill_path = shutil.which("pkill")
            if pkill_path:
                subprocess.run([pkill_path, "-f", "gemini --extensions \"\" -m"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL) # nosec B603
        except Exception: pass

if __name__ == "__main__":
    from ledgermind.core.core.schemas import TrustBoundary
    parser = argparse.ArgumentParser(description="LedgerMind Standalone Worker")
    parser.add_argument("--storage", required=True, help="Absolute path to storage")
    parser.add_argument("--log", help="Absolute path to log file")
    args = parser.parse_args()

    storage_abs = os.path.abspath(args.storage)
    memory = Memory(storage_path=storage_abs, trust_boundary=TrustBoundary.AGENT_WITH_INTENT)
    log_abs = os.path.abspath(args.log) if args.log else None
    worker = BackgroundWorker(memory, log_path=log_abs)
    worker.run_forever()
