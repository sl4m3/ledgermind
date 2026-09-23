"""Background lease heartbeat helper."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class LeaseHeartbeat:
    def __init__(
        self, refresh: Callable[[], object], *, interval_seconds: float
    ) -> None:
        self.refresh = refresh
        self.interval_seconds = max(float(interval_seconds), 0.1)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="ledgermind-lease-heartbeat", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds + 1.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.refresh()
            except Exception as exc:  # noqa: BLE001
                logger.debug("lease heartbeat failed: %s", type(exc).__name__)


__all__ = ["LeaseHeartbeat"]
