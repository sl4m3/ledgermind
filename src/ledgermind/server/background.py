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

from ledgermind.server.workers import EnrichmentWorker, ReflectionWorker
from ledgermind.server.workers.coordinator import WorkerCoordinator

logger = logging.getLogger("ledgermind.worker")

class BackgroundWorker:
    """
    Active Runtime Loop ("The Heartbeat") for LedgerMind.
    Designed to run as a standalone, detached process.
    Supports graceful shutdown and lock file monitoring.
    
    Architecture:
    - Runs as a separate process (via __main__)
    - Manages multiple worker threads for parallel execution:
      - ReflectionWorker: Every 5 minutes (reflection, promotion, decay, merge)
      - EnrichmentWorker: Every 1 minute (LLM enrichment of pending items)
      - WatchdogThread: Every 10 seconds (lock file monitoring)
    - Main thread acts as manager and session monitor
    """
    def __init__(self, memory: Memory, interval_seconds: int = 300, log_path: Optional[str] = None):
        self.memory = memory
        self.memory.storage_path = os.path.abspath(self.memory.storage_path)

        self.interval = interval_seconds  # Maintenance interval (5 min default)

        # Determine log path (default to storage/logs/worker.log)
        if log_path is None:
            log_dir = os.path.join(self.memory.storage_path, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "worker.log")
        
        self._setup_logging(os.path.abspath(log_path))

        self.running = False
        self._stop_event = threading.Event()

        # Coordinator для управления доступом воркеров
        self.coordinator = WorkerCoordinator()

        # Worker threads
        self.enrichment_worker: Optional[EnrichmentWorker] = None
        self.reflection_worker: Optional[ReflectionWorker] = None
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
        """Configure root logger with file and (optional) console handlers."""
        log_dir = os.path.dirname(log_path)
        if log_dir: os.makedirs(log_dir, exist_ok=True)
        
        root_logger = logging.getLogger()
        # Remove existing handlers to avoid duplicates
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # File handler (overwrite mode for fresh start)
        fh = logging.FileHandler(log_path, mode='w')
        fh.setFormatter(formatter)
        root_logger.addHandler(fh)
        
        # Console handler if running in foreground (tty)
        if sys.stderr.isatty():
            ch = logging.StreamHandler(sys.stderr)
            ch.setFormatter(formatter)
            root_logger.addHandler(ch)
        
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

        # 1. Start enrichment worker (every 60s, 10s initial delay)
        self.enrichment_worker = EnrichmentWorker(
            stop_event=self._stop_event,
            memory=self.memory,
            interval_seconds=60,
            initial_delay=10.0,
            coordinator=self.coordinator,
        )
        self.enrichment_worker.start()

        # 2. Start reflection worker (every 300s, 30s initial delay)
        self.reflection_worker = ReflectionWorker(
            stop_event=self._stop_event,
            memory=self.memory,
            interval_seconds=self.interval,
            initial_delay=30.0,
            coordinator=self.coordinator,
        )
        self.reflection_worker.start()

        # 3. Start watchdog thread (10s interval)
        self.watchdog_thread = threading.Thread(target=self._lock_watchdog, name="WorkerWatchdog", daemon=True)
        self.watchdog_thread.start()

        logger.info("Background Worker started (Workers: Reflection=5min, Enrichment=1min, Watchdog=10s).")

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

        # 1. Shutdown worker threads gracefully
        logger.info("Stopping worker threads...")

        # Log coordinator stats before shutdown
        if self.coordinator:
            stats = self.coordinator.stats
            logger.info(f"Coordinator stats: enrichment={stats['enrichment_completed']}/{stats['enrichment_started']}, "
                       f"reflection={stats['reflection_completed']}/{stats['reflection_started']}, "
                       f"skipped={stats['reflection_skipped']}, wait_time={stats['reflection_wait_total_sec']}s")
            self.coordinator.force_stop_all()

        if self.enrichment_worker:
            self.enrichment_worker.shutdown()
            self.enrichment_worker.join(timeout=timeout / 2)
            
        if self.reflection_worker:
            self.reflection_worker.shutdown()
            self.reflection_worker.join(timeout=timeout / 2)

        # 2. Kill all registered gemini subprocesses immediately
        with self._proc_lock:
            if self._active_subprocesses:
                logger.info(f"Killing {len(self._active_subprocesses)} active subprocesses...")
                for proc in self._active_subprocesses:
                    try:
                        if proc.poll() is None:
                            proc.kill() # Direct kill for speed
                    except Exception: pass
                self._active_subprocesses.clear()

        # 3. Release lock and remove worker.pid
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

    def run_forever(self):
        """
        Main worker loop - acts as manager and session monitor.
        
        Worker threads handle periodic tasks in parallel:
        - ReflectionWorker: maintenance every 5 minutes
        - EnrichmentWorker: LLM enrichment every 1 minute
        - WatchdogThread: lock file monitoring every 10 seconds
        
        Main thread only monitors sessions and lock file health.
        """
        try:
            self.start()
            lock_path = os.path.join(self.memory.storage_path, "worker.pid")

            while self.running:
                # 0. CRITICAL: Lock file health check (Manual removal detection)
                if not os.path.exists(lock_path):
                    logger.warning("Worker lock file (worker.pid) deleted manually. Shutting down.")
                    break

                # RESPONSIVE SLEEP
                # Check lock file every 5 seconds, sleep for ~100 seconds total
                for _ in range(20):
                    if not self.running or not os.path.exists(lock_path):
                        break
                    if self._stop_event.wait(5.0):
                        break

        except Exception as fatal_e:
            logger.critical(f"FATAL: Worker loop crashed: {fatal_e}", exc_info=True)
        finally:
            self.stop()

    def _cleanup_orphans(self):
        try:
            subprocess.run("pkill -f 'gemini --extensions \"\" -m'", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
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