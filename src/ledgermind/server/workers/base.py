import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional, Any

logger = logging.getLogger("ledgermind.worker.base")


class WorkerThread(threading.Thread, ABC):
    """
    Base class for background worker threads.
    
    Provides a reusable pattern for periodic task execution with:
    - Configurable interval between runs
    - Graceful shutdown support via stop_event
    - Error handling and logging
    - Responsive sleep (checks stop_event frequently)
    """
    
    def __init__(
        self,
        name: str,
        interval_seconds: int,
        stop_event: threading.Event,
        memory: Any,
        initial_delay: float = 0.0,
    ):
        super().__init__(name=name, daemon=True)
        self.name = name
        self.interval = interval_seconds
        self.stop_event = stop_event
        self.memory = memory
        self.initial_delay = initial_delay
        self.running = False
        
    def run(self):
        """Main worker loop with initial delay and periodic execution."""
        logger.info(f"[{self.name}] Worker thread started (interval={self.interval}s)")
        
        # Initial delay if specified
        if self.initial_delay > 0:
            logger.info(f"[{self.name}] Waiting {self.initial_delay}s before first run...")
            if self._responsive_sleep(self.initial_delay):
                return  # Shutdown requested
        
        self.running = True
        
        while self.running and not self.stop_event.is_set():
            try:
                start_time = time.time()
                
                # Execute the actual work
                self.do_work()
                
                # Calculate remaining time and sleep responsively
                elapsed = time.time() - start_time
                wait_time = max(1.0, self.interval - elapsed)
                
                if self._responsive_sleep(wait_time):
                    break  # Shutdown requested
                    
            except Exception as e:
                logger.error(f"[{self.name}] Error in worker loop: {e}", exc_info=True)
                # Don't exit on error - continue with next interval
                if self.stop_event.wait(5.0):
                    break
        
        self.running = False
        logger.info(f"[{self.name}] Worker thread stopped")
    
    def _responsive_sleep(self, duration: float) -> bool:
        """
        Sleep for duration but check stop_event frequently.
        Returns True if shutdown was requested, False otherwise.
        """
        sleep_interval = 0.5  # Check every 500ms
        iterations = int(duration / sleep_interval)
        
        for _ in range(iterations):
            if self.stop_event.is_set() or not self.running:
                return True
            time.sleep(sleep_interval)
        
        return self.stop_event.is_set() or not self.running
    
    @abstractmethod
    def do_work(self):
        """
        Execute the actual work for this worker.
        Must be implemented by subclasses.
        """
        pass
    
    def shutdown(self):
        """Request graceful shutdown of this worker."""
        logger.info(f"[{self.name}] Shutdown requested")
        self.running = False
