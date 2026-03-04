import logging
import time
import os
import threading
from typing import Optional, Dict, List, Any
from datetime import datetime

from ledgermind.core.api.memory import Memory

logger = logging.getLogger(__name__)

class BackgroundWorker:
    """
    Active Runtime Loop ("The Heartbeat") for LedgerMind.
    Ensures the system is always alive, healthy, and evolving.
    Uses multi-threading for independent maintenance and enrichment cycles.
    """
    def __init__(self, memory: Memory, interval_seconds: int = 300):
        self.memory = memory
        self.interval = interval_seconds
        self.enrichment_interval = 60 # Check enrichment queue more frequently
        
        # Setup specific file logging for the background worker (only if not already setup)
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        root_logger = logging.getLogger("ledgermind")
        
        # Check if FileHandler already exists to avoid duplicates
        has_fh = any(isinstance(h, logging.FileHandler) and "background_worker.log" in str(h.baseFilename) for h in root_logger.handlers)
        
        if not has_fh:
            fh = logging.FileHandler(os.path.join(log_dir, "background_worker.log"))
            fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            root_logger.addHandler(fh)
            root_logger.setLevel(logging.INFO)
        
        self.running = False
        self.maintenance_thread: Optional[threading.Thread] = None
        self.enrichment_thread: Optional[threading.Thread] = None
        
        self.last_run: Dict[str, datetime] = {}
        self.status = "stopped"
        self.errors: List[str] = []
        self._active_subprocesses: List[Any] = []
        self._proc_lock = threading.Lock()

    def start(self):
        if self.running: return

        # 0. Cleanup orphaned enrichment processes from previous crashes
        self._cleanup_orphans()

        # 1. Prevent multiple workers from running against the same storage
        is_running, other_pid = self._is_worker_running()
        if is_running:
            if other_pid == os.getpid():
                return
            logger.info(f"Background Worker is already handled by process {other_pid}. Skipping.")
            self.status = "busy"
            return

        self.running = True
        self.status = "running"
        self._create_lock()
        
        # 1. Main Maintenance Thread (Integrity, Reflection, Decay, Merge)
        self.maintenance_thread = threading.Thread(
            target=self._maintenance_loop, 
            name="LedgermindMaintenanceWorker", 
            daemon=True
        )
        self.maintenance_thread.start()
        
        # 2. Enrichment Thread (LLM Processing)
        self.enrichment_thread = threading.Thread(
            target=self._enrichment_loop,
            name="LedgermindEnrichmentWorker",
            daemon=True
        )
        self.enrichment_thread.start()
        
        logger.info("Background Worker started (Maintenance & Enrichment).")

    def _cleanup_orphans(self):
        """Kills any stray 'gemini' enrichment processes left from previous crashes."""
        import subprocess
        try:
            # Kill processes launched with '-m' (enrichment mode) to avoid affecting main CLI
            subprocess.run("pkill -f 'gemini -m'", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            logger.info("Cleaned up orphaned enrichment processes.")
        except Exception:
            pass

    def stop(self):
        """Gracefully (and forcefully if needed) stops the worker and its children."""
        self.running = False
        
        # Terminate any active subprocesses (Gemini CLI calls)
        with self._proc_lock:
            if self._active_subprocesses:
                logger.info(f"Terminating {len(self._active_subprocesses)} active subprocesses...")
                for proc in self._active_subprocesses:
                    try:
                        if proc.poll() is None: # Still running
                            proc.terminate()
                            # Give it a moment to terminate gracefully, then kill
                            threading.Timer(2.0, lambda p=proc: p.kill() if p.poll() is None else None).start()
                    except Exception as e:
                        logger.debug(f"Failed to terminate subprocess: {e}")
                self._active_subprocesses.clear()

        if self.maintenance_thread and self.maintenance_thread.is_alive():
            self.maintenance_thread.join(timeout=2.0)
        if self.enrichment_thread and self.enrichment_thread.is_alive():
            self.enrichment_thread.join(timeout=2.0)
        self.status = "stopped"
        self._remove_lock()
        logger.info("Background Worker stopped.")

    def register_process(self, proc: Any):
        """Registers a subprocess for cleanup on stop."""
        with self._proc_lock:
            self._active_subprocesses.append(proc)

    def unregister_process(self, proc: Any):
        """Unregisters a subprocess after completion."""
        with self._proc_lock:
            if proc in self._active_subprocesses:
                self._active_subprocesses.remove(proc)

    def _is_worker_running(self) -> tuple[bool, Optional[int]]:
        """Checks if a worker is already running for this storage path. Returns (is_running, pid)."""
        pid_file = os.path.join(self.memory.storage_path, "worker.pid")
        if not os.path.exists(pid_file):
            return False, None
        
        try:
            with open(pid_file, 'r') as f:
                content = f.read().strip()
                if not content: return False, None
                pid = int(content)
            
            # Check if process is alive (Unix/Android)
            os.kill(pid, 0)
            
            # Verify it's actually a Ledgermind process to handle PID reuse
            try:
                if os.path.exists(f"/proc/{pid}/cmdline"):
                    with open(f"/proc/{pid}/cmdline", "r") as f_cmd:
                        cmdline = f_cmd.read().lower()
                        # If PID is reused by something else, treat lock as stale
                        if "python" not in cmdline and "ledgermind" not in cmdline:
                            logger.warning(f"PID {pid} in lock is not Ledgermind. Reclaiming.")
                            return False, None
            except Exception:
                pass
                
            return True, pid
        except (OSError, ValueError):
            # If process is not alive or file is corrupt, treat as not running
            return False, None

    def _create_lock(self):
        """Creates a PID file to lock this storage for current process."""
        pid_file = os.path.join(self.memory.storage_path, "worker.pid")
        try:
            with open(pid_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            logger.warning(f"Could not create worker lock file: {e}")

    def _remove_lock(self):
        """Removes the PID lock file."""
        pid_file = os.path.join(self.memory.storage_path, "worker.pid")
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except Exception as e:
                logger.debug(f"Could not remove worker lock file: {e}")

    def _maintenance_loop(self):
        """Cycle for core system maintenance tasks."""
        # Initial grace period
        time.sleep(2)
        
        while self.running:
            try:
                start_time = time.time()
                
                # 1. Health Check & Self-Healing
                self._run_health_check()
                
                # 2. Git Sync (Ingest external changes)
                self._run_git_sync()
                
                # 3. Core Maintenance Cycle (Reflection, Decay, Integrity, Merging)
                self._run_maintenance()
                
                elapsed = time.time() - start_time
                sleep_time = max(1.0, self.interval - elapsed)
                
                for _ in range(int(sleep_time)):
                    if not self.running: break
                    time.sleep(1)
                
            except Exception as e:
                if "no such table" in str(e).lower():
                    logger.debug("Maintenance Loop: Database not initialized yet. Waiting...")
                    time.sleep(10)
                    continue

                logger.error(f"Maintenance Loop crashed: {e}")
                self.errors.append(f"Maint-{datetime.now()}: {str(e)}")
                time.sleep(60)

    def _enrichment_loop(self):
        """Cycle for LLM enrichment tasks. Runs independently of core maintenance."""
        # Longer grace period to let maintenance finish initial syncs
        time.sleep(15)
        
        while self.running:
            try:
                start_time = time.time()
                
                # Use self.memory directly - our SQLite stores are configured 
                # with check_same_thread=False, making them thread-safe.
                # Dual initialization of Memory/VectorStore causes OpenMP crashes.
                arbitration_mode = self.memory.semantic.meta.get_config("arbitration_mode", "lite")
                
                if arbitration_mode != "lite":
                    from ledgermind.core.reasoning.llm_enrichment import LLMEnricher
                    enricher = LLMEnricher(mode=arbitration_mode, worker=self)
                    
                    try:
                        logger.info(f"Starting Enrichment Cycle (mode={arbitration_mode})...")
                        results = enricher.process_batch(self.memory)
                        
                        if results:
                            for res in results:
                                logger.info(f"Background Enrichment: {res['fid']} ({res['status']}, {res['events']} events)")
                        
                        self.last_run["enrichment"] = datetime.now()
                    finally:
                        enricher.close()
                
                elapsed = time.time() - start_time
                sleep_time = max(5.0, self.enrichment_interval - elapsed)
                
                for _ in range(int(sleep_time)):
                    if not self.running: break
                    time.sleep(1)
                    
            except Exception as e:
                if "no such table" in str(e).lower():
                    time.sleep(15)
                    continue
                
                logger.error(f"Enrichment Loop crashed: {e}")
                self.errors.append(f"Enrich-{datetime.now()}: {str(e)}")
                time.sleep(120)

    def _run_health_check(self):
        """Monitors system health and attempts repairs."""
        try:
            health = self.memory.check_environment()
            
            # Auto-Heal: Stale Locks
            if health.get("storage_locked"):
                lock_path = os.path.join(self.memory.semantic.repo_path, ".lock")
                if os.path.exists(lock_path):
                    mtime = os.path.getmtime(lock_path)
                    age = time.time() - mtime
                    if age > 600: # 10 minutes
                        logger.warning(f"Breaking stale lock file (age: {age}s)")
                        try:
                            os.remove(lock_path)
                            logger.info("Stale lock removed.")
                        except Exception as ex:
                            logger.error(f"Failed to remove stale lock: {ex}")
            
            self.last_run["health"] = datetime.now()
        except Exception as e:
            logger.error(f"Health check failed: {e}")

    def _run_git_sync(self):
        """Syncs recent git commits to episodic memory."""
        try:
            if self.memory._git_available:
                # In origin/main it syncs repo_path=".", limit=5
                count = self.memory.sync_git(repo_path=".", limit=5)
                if isinstance(count, int) and count > 0:
                    logger.info(f"Background Sync: Indexed {count} commits.")
                self.last_run["git_sync"] = datetime.now()
        except Exception as e:
            if "no such table" in str(e).lower(): raise e
            logger.warning(f"Git sync failed: {e}")

    def _run_maintenance(self):
        """Runs the core maintenance cycle including reflection and decay."""
        try:
            last = self.last_run.get("maintenance")
            now = datetime.now()
            
            # Run maintenance every 5 minutes
            if not last or (now - last).total_seconds() > 300:
                report = self.memory.run_maintenance()
                
                refl_count = report.get("reflection", {}).get("proposals_created", 0)
                decay_archived = report.get("decay", {}).get("archived", 0)
                decay_pruned = report.get("decay", {}).get("pruned", 0)
                
                msgs = []
                if refl_count > 0: msgs.append(f"Reflected {refl_count} items")
                if decay_archived > 0 or decay_pruned > 0: msgs.append(f"Decayed (Arch: {decay_archived}, Prun: {decay_pruned})")
                
                if msgs:
                    logger.info(f"Background Maintenance: {', '.join(msgs)}")
                
                self.last_run["maintenance"] = now
        except Exception as e:
            if "no such table" in str(e).lower(): raise e
            logger.error(f"Maintenance cycle failed: {e}")
