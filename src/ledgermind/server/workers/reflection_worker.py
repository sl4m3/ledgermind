import logging
import threading
from typing import Any, Optional

from .base import WorkerThread
from .coordinator import WorkerCoordinator

logger = logging.getLogger("ledgermind.worker.reflection")


class ReflectionWorker(WorkerThread):
    """
    Worker thread for reflection and knowledge maintenance.

    Runs every 300 seconds (5 minutes) to:
    1. Run integrity checks
    2. Execute reflection cycle (analyze patterns from episodic memory)
    3. Run promotion (advance decision phases)
    4. Apply vitality decay
    5. Handle knowledge merging
    
    Coordinator integration:
    - Uses coordinator.reflection_context() to wait for Enrichment to complete
    - Reflection waits up to 300s for Enrichment to finish
    - Skips cycle if timeout exceeded (graceful degradation)
    """

    def __init__(
        self,
        stop_event: threading.Event,
        memory: Any,
        interval_seconds: int = 300,
        initial_delay: float = 30.0,
        coordinator: Optional[WorkerCoordinator] = None,
    ):
        super().__init__(
            name="ReflectionWorker",
            interval_seconds=interval_seconds,
            stop_event=stop_event,
            memory=memory,
            initial_delay=initial_delay,
        )
        self.coordinator = coordinator

    def do_work(self):
        """Execute reflection and maintenance cycle."""
        # Если coordinator есть, использовать контекст
        if self.coordinator:
            try:
                with self.coordinator.reflection_context(timeout=300.0, skip_if_busy=True):
                    self._do_reflection()
            except TimeoutError as e:
                logger.warning(f"[ReflectionWorker] Skipped: {e}")
        else:
            self._do_reflection()

    def _do_reflection(self):
        """Выполнить reflection (внутри coordinator context)."""
        try:
            logger.info("[ReflectionWorker] Starting maintenance cycle...")

            # Run full maintenance cycle (reflection, promotion, decay, merge)
            self.memory.check_environment()
            result = self.memory.run_maintenance(stop_event=self.stop_event)

            # Log results summary
            if result:
                logger.info(f"[ReflectionWorker] Maintenance completed: {result}")
            else:
                logger.info("[ReflectionWorker] Maintenance completed")

        except Exception as e:
            logger.error(f"[ReflectionWorker] Maintenance cycle failed: {e}", exc_info=True)
            # Don't re-raise - allow worker to continue on next interval
