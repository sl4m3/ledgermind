"""Bounded background loop for Hermes capture promotion and delivery."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..adapters.hermes.hooks import PendingCaptureWorker
from .delivery import DeliveryWorker

logger = logging.getLogger(__name__)


class HermesWorkerLoop:
    def __init__(
        self,
        *,
        delivery_worker: DeliveryWorker,
        pending_worker: PendingCaptureWorker,
        pending_resolver: Callable[[Mapping[str, Any]], Sequence[Mapping[str, Any]] | None],
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self.delivery_worker = delivery_worker
        self.pending_worker = pending_worker
        self.pending_resolver = pending_resolver
        self.poll_interval_seconds = max(float(poll_interval_seconds), 0.05)
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def thread(self) -> threading.Thread | None:
        return self._thread

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self.stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ledgermind-hermes-worker",
            daemon=False,
        )
        self._thread.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self.stop_event.set()
        self.wake_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(float(timeout_seconds), 0.1))

    def wake(self) -> None:
        self.wake_event.set()

    def run_once(self) -> bool:
        did_work = False
        try:
            did_work = self.pending_worker.run_once(self.pending_resolver) > 0 or did_work
        except Exception as exc:  # noqa: BLE001
            logger.warning("pending capture cycle failed: %s", type(exc).__name__)
        try:
            did_work = self.delivery_worker.run_once() or did_work
        except Exception as exc:  # noqa: BLE001
            logger.warning("delivery cycle failed: %s", type(exc).__name__)
        return did_work

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.run_once()
            self.wake_event.wait(self.poll_interval_seconds)
            self.wake_event.clear()
        # One bounded final cycle makes already-promoted captures visible to
        # the delivery worker without keeping shutdown open indefinitely.
        self.run_once()


__all__ = ["HermesWorkerLoop"]
