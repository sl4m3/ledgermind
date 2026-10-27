"""Results returned by Local worker shutdown attempts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkerShutdownResult:
    """Observable outcome of requesting a worker loop to stop.

    A timed-out result deliberately does not imply that the worker thread stopped
    or that resources used by that worker are safe to close.
    """

    stopped: bool
    timed_out: bool
    thread_name: str | None
    current_item_id: str | None


__all__ = ["WorkerShutdownResult"]
