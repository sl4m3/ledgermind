import logging
import threading
from typing import Any, Optional

from .base import WorkerThread

logger = logging.getLogger("ledgermind.worker.enrichment")


class EnrichmentWorker(WorkerThread):
    """
    Worker thread for LLM-based enrichment of pending knowledge items.
    
    Runs every 60 seconds to:
    1. Check for items with enrichment_status='pending'
    2. Process them using LLMEnricher
    3. Update enrichment status upon completion
    """
    
    def __init__(
        self,
        stop_event: threading.Event,
        memory: Any,
        interval_seconds: int = 60,
        initial_delay: float = 10.0,
    ):
        super().__init__(
            name="EnrichmentWorker",
            interval_seconds=interval_seconds,
            stop_event=stop_event,
            memory=memory,
            initial_delay=initial_delay,
        )
        self._enricher: Optional[Any] = None
        
    def do_work(self):
        """Execute LLM enrichment for pending items."""
        try:
            # Get current mode from memory config
            mode = self.memory.semantic.meta.get_config("arbitration_mode", "optimal")
            
            if mode == "lite":
                logger.debug("[EnrichmentWorker] Skipping: lite mode active")
                return
            
            logger.info(f"[EnrichmentWorker] Starting enrichment cycle (mode={mode})")
            
            # Import here to avoid circular imports
            from ledgermind.core.reasoning.enrichment import LLMEnricher
            
            # Create enricher and process batch
            self._enricher = LLMEnricher(mode=mode)
            
            try:
                self._enricher.run_auto_enrichment(self.memory)
                logger.info("[EnrichmentWorker] Enrichment cycle completed")
            finally:
                self._close_enricher()
                
        except Exception as e:
            logger.error(f"[EnrichmentWorker] Enrichment cycle failed: {e}", exc_info=True)
            # Ensure cleanup on error
            self._close_enricher()
    
    def _close_enricher(self):
        """Safely close the enricher and release resources."""
        if self._enricher:
            try:
                # Call close() if the enricher has this method
                if hasattr(self._enricher, "close"):
                    self._enricher.close()
            except Exception as e:
                logger.warning(f"[EnrichmentWorker] Error closing enricher: {e}")
            finally:
                self._enricher = None
    
    def shutdown(self):
        """Graceful shutdown with enricher cleanup."""
        logger.info("[EnrichmentWorker] Initiating graceful shutdown...")
        self._close_enricher()
        super().shutdown()
