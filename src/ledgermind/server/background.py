import logging
import time
import os
import threading
from typing import Optional, Dict, List
from datetime import datetime

from ledgermind.core.api.memory import Memory

logger = logging.getLogger(__name__)

class BackgroundWorker:
    """
    Active Runtime Loop ("The Heartbeat") for LedgerMind.
    Ensures the system is always alive, healthy, and evolving.
    Uses threading for compatibility with sync/async environments.
    """
    def __init__(self, memory: Memory, interval_seconds: int = 300):
        self.memory = memory
        self.interval = interval_seconds
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_run: Dict[str, datetime] = {}
        self.status = "stopped"
        self.errors: List[str] = []

    def start(self):
        if self.running: return
        self.running = True
        self.status = "running"
        self.thread = threading.Thread(target=self._loop, name="LedgermindBackgroundWorker", daemon=True)
        self.thread.start()
        logger.info("Background Worker started.")

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.status = "stopped"
        logger.info("Background Worker stopped.")

    def _loop(self):
        # Initial grace period (Reduced for faster responsiveness in tests)
        time.sleep(2)
        
        while self.running:
            try:
                start_time = time.time()
                
                # 1. Health Check & Self-Healing
                self._run_health_check()
                
                # 2. Git Sync (Ingest external changes)
                self._run_git_sync()
                
                # 3. Full Maintenance Cycle (Reflection, Decay, Enrichment, Integrity)
                self._run_maintenance()
                
                elapsed = time.time() - start_time
                sleep_time = max(1.0, self.interval - elapsed)
                
                # Sleep in chunks to allow faster stopping
                for _ in range(int(sleep_time)):
                    if not self.running: break
                    time.sleep(1)
                
            except Exception as e:
                # Handle SQLite not ready yet or other startup race conditions
                if "no such table" in str(e).lower():
                    logger.debug("Background Worker: Database not initialized yet. Waiting...")
                    time.sleep(5)
                    continue

                logger.error(f"Background Worker crashed: {e}")
                self.errors.append(f"{datetime.now()}: {str(e)}")
                time.sleep(60) # Backoff on crash

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
            # Sync only if git is available and configured
            if self.memory._git_available:
                count = self.memory.sync_git(repo_path=".", limit=5)
                if isinstance(count, int) and count > 0:
                    logger.info(f"Background Sync: Indexed {count} commits.")
                self.last_run["git_sync"] = datetime.now()
        except Exception as e:
            if "no such table" in str(e).lower(): raise e
            logger.warning(f"Git sync failed: {e}")

    def _run_maintenance(self):
        """Runs the full maintenance cycle including reflection, decay, and enrichment."""
        try:
            # Run full maintenance every 5 minutes
            last = self.last_run.get("maintenance")
            now = datetime.now()
            
            if not last or (now - last).total_seconds() > 300: # 5 minutes
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
