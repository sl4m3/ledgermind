"""One-shot raw payload retention worker for the Local service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ledgermind_local.persistence import SQLiteUnitOfWork


@dataclass(frozen=True, slots=True)
class RetentionResult:
    """Committed result of one bounded raw payload cleanup pass."""

    purged: int

    @property
    def purged_payloads(self) -> int:
        """Compatibility name for callers that use the domain noun."""

        return self.purged

    @property
    def deleted_payloads(self) -> int:
        """Compatibility name for metrics/reporting consumers."""

        return self.purged


class RawRoundRetentionWorker:
    """Purge expired payload bodies without starting a scheduling thread."""

    def __init__(self, database_path: str | Path, *, busy_timeout_ms: int = 5_000) -> None:
        self.database_path = database_path
        self.busy_timeout_ms = max(int(busy_timeout_ms), 1)

    def process_once(self, now: str | None = None, limit: int = 100) -> RetentionResult:
        """Run one short write transaction and return its committed purge count."""

        bounded_limit = int(limit)
        if bounded_limit < 1:
            raise ValueError("limit must be positive")
        with SQLiteUnitOfWork(
            self.database_path,
            busy_timeout_ms=self.busy_timeout_ms,
            write_transaction=True,
        ) as uow:
            purged = uow.raw_rounds.purge_expired(now=now, limit=bounded_limit)
            uow.commit()
        return RetentionResult(purged=purged)


__all__ = ["RawRoundRetentionWorker", "RetentionResult"]
