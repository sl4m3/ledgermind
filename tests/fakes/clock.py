"""Deterministic clock fake for tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from ledgermind_core.ports import Clock


class FakeClock(Clock):
    def __init__(self, initial: datetime):
        self._current = initial

    def now(self) -> datetime:
        return self._current

    def tick(self, delta: timedelta) -> None:
        self._current += delta
