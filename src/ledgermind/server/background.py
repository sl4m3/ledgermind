import logging
import threading
from typing import Optional, Any

from ledgermind.server.workers import EnrichmentWorker, ReflectionWorker
from ledgermind.server.workers.coordinator import WorkerCoordinator

logger = logging.getLogger("ledgermind.worker")


class BackgroundWorker:
    """
    Lightweight background worker for Hermes plugin.

    Manages two worker threads:
    - EnrichmentWorker: every 60s (LLM enrichment of pending items)
    - ReflectionWorker: every 5min (reflection, promotion, decay, merge)

    Lifecycle controlled by plugin hooks:
    - on_session_start → start()
    - on_session_end → stop()
    """

    def __init__(self, memory: Any, interval_seconds: int = 300, client: Optional[str] = None):
        self.memory = memory
        self.client = client
        self.interval = interval_seconds
        self.running = False
        self._stop_event = threading.Event()
        self.coordinator = WorkerCoordinator()
        self.enrichment_worker: Optional[EnrichmentWorker] = None
        self.reflection_worker: Optional[ReflectionWorker] = None

    def start(self):
        if self.running:
            return

        self.running = True
        self._stop_event.clear()

        self.enrichment_worker = EnrichmentWorker(
            stop_event=self._stop_event,
            memory=self.memory,
            interval_seconds=60,
            initial_delay=10.0,
            coordinator=self.coordinator,
        )
        self.enrichment_worker.start()

        self.reflection_worker = ReflectionWorker(
            stop_event=self._stop_event,
            memory=self.memory,
            interval_seconds=self.interval,
            initial_delay=30.0,
            coordinator=self.coordinator,
        )
        self.reflection_worker.start()

        logger.info("Background worker started")

    def stop(self):
        if not self.running:
            return

        self.running = False
        self._stop_event.set()

        if self.coordinator:
            self.coordinator.force_stop_all()

        if self.enrichment_worker:
            self.enrichment_worker.shutdown()
            self.enrichment_worker.join(timeout=2.5)

        if self.reflection_worker:
            self.reflection_worker.shutdown()
            self.reflection_worker.join(timeout=2.5)

        logger.info("Background worker stopped")
