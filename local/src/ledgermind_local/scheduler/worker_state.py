"""Thread-safe runtime state for Local background workers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from threading import RLock


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class WorkerStateSnapshot:
    """Immutable point-in-time view of a worker's runtime state."""

    name: str
    running: bool = False
    healthy: bool = True
    last_started_at: str | None = None
    last_success_at: str | None = None
    last_error_at: str | None = None
    last_error_code: str | None = None
    consecutive_failures: int = 0
    processed_count: int = 0
    failed_count: int = 0
    current_item_id: str | None = None
    stopping: bool = False
    shutdown_timed_out: bool = False
    last_progress_at: str | None = None
    last_iteration_failure_count: int = 0
    degraded: bool = False


@dataclass(frozen=True, slots=True)
class WorkerOutcome:
    """Immutable result and state snapshot published for one iteration."""

    result: object | None
    snapshot: WorkerStateSnapshot


class WorkerState:
    """Mutable worker state whose snapshots are safe across threads."""

    def __init__(self, name: str) -> None:
        if not name.strip():
            raise ValueError("worker state name must not be empty")
        self._lock = RLock()
        self._snapshot = WorkerStateSnapshot(name=name)
        self._last_outcome: WorkerOutcome | None = None

    def snapshot(self) -> WorkerStateSnapshot:
        """Return an immutable copy of the current state."""

        with self._lock:
            return replace(self._snapshot)

    @property
    def last_outcome(self) -> WorkerOutcome | None:
        """Return the last successful outcome published with this state."""

        with self._lock:
            return self._last_outcome

    @property
    def name(self) -> str:
        return self.snapshot().name

    @property
    def running(self) -> bool:
        return self.snapshot().running

    @property
    def healthy(self) -> bool:
        return self.snapshot().healthy

    @property
    def last_started_at(self) -> str | None:
        return self.snapshot().last_started_at

    @property
    def last_success_at(self) -> str | None:
        return self.snapshot().last_success_at

    @property
    def last_error_at(self) -> str | None:
        return self.snapshot().last_error_at

    @property
    def last_error_code(self) -> str | None:
        return self.snapshot().last_error_code

    @property
    def consecutive_failures(self) -> int:
        return self.snapshot().consecutive_failures

    @property
    def processed_count(self) -> int:
        return self.snapshot().processed_count

    @property
    def failed_count(self) -> int:
        return self.snapshot().failed_count

    @property
    def current_item_id(self) -> str | None:
        return self.snapshot().current_item_id

    @property
    def stopping(self) -> bool:
        return self.snapshot().stopping

    @property
    def shutdown_timed_out(self) -> bool:
        return self.snapshot().shutdown_timed_out

    @property
    def last_progress_at(self) -> str | None:
        return self.snapshot().last_progress_at

    @property
    def last_iteration_failure_count(self) -> int:
        return self.snapshot().last_iteration_failure_count

    @property
    def degraded(self) -> bool:
        return self.snapshot().degraded

    def mark_started(self, *, item_id: str | None = None) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                running=True,
                stopping=False,
                shutdown_timed_out=False,
                last_started_at=_now(),
                current_item_id=item_id,
            )

    def set_current_item(self, item_id: str | None) -> None:
        with self._lock:
            self._snapshot = replace(self._snapshot, current_item_id=item_id)

    def mark_progress(self) -> None:
        """Record that the worker completed observable progress."""

        with self._lock:
            self._snapshot = replace(self._snapshot, last_progress_at=_now())

    def mark_degraded(self, degraded: bool = True) -> None:
        """Set the degraded marker without storing error details or payloads."""

        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                degraded=bool(degraded),
                healthy=False if degraded else self._snapshot.healthy,
            )

    set_degraded = mark_degraded

    def mark_stopping(self) -> None:
        with self._lock:
            self._snapshot = replace(self._snapshot, stopping=True)

    def mark_shutdown_timed_out(self) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                stopping=True,
                shutdown_timed_out=True,
                healthy=False,
                degraded=True,
            )

    def publish_result(
        self,
        result: object | None,
        *,
        item_id: str | None = None,
        processed: bool = True,
        degraded: bool = False,
    ) -> WorkerOutcome:
        """Publish one successful iteration and return its immutable outcome.

        The degraded flag is committed with the normal success counters before
        any result observer can publish its own diagnostic observation. This
        keeps the health-facing state from briefly reporting healthy for a
        result that has already been classified as degraded.
        """

        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                running=True,
                healthy=not degraded,
                degraded=bool(degraded),
                last_success_at=_now(),
                consecutive_failures=0,
                last_iteration_failure_count=0,
                last_progress_at=_now(),
                processed_count=(
                    self._snapshot.processed_count + (1 if processed else 0)
                ),
                current_item_id=item_id,
            )
            outcome = WorkerOutcome(result=result, snapshot=replace(self._snapshot))
            self._last_outcome = outcome
            return outcome

    def mark_success(
        self,
        *,
        item_id: str | None = None,
        processed: bool = True,
    ) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                running=True,
                healthy=True,
                degraded=False,
                last_success_at=_now(),
                consecutive_failures=0,
                last_iteration_failure_count=0,
                last_progress_at=_now(),
                processed_count=(
                    self._snapshot.processed_count + (1 if processed else 0)
                ),
                current_item_id=item_id,
            )

    def mark_error(
        self,
        error_code: str,
        *,
        item_id: str | None = None,
        failure_count: int | None = None,
    ) -> None:
        if not error_code.strip():
            raise ValueError("worker error code must not be empty")
        if failure_count is not None and failure_count < 1:
            raise ValueError("failure_count must be positive")
        with self._lock:
            consecutive_failures = self._snapshot.consecutive_failures + 1
            self._snapshot = replace(
                self._snapshot,
                running=True,
                healthy=False,
                degraded=True,
                last_error_at=_now(),
                last_error_code=error_code,
                consecutive_failures=consecutive_failures,
                last_iteration_failure_count=failure_count or consecutive_failures,
                failed_count=self._snapshot.failed_count + 1,
                current_item_id=item_id,
            )

    def mark_stopped(self) -> None:
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                running=False,
                stopping=False,
                current_item_id=None,
            )

    def as_dict(self) -> dict[str, object]:
        """Return a serialization-friendly snapshot without mutable internals."""

        return asdict(self.snapshot())


__all__ = ["WorkerOutcome", "WorkerState", "WorkerStateSnapshot"]
