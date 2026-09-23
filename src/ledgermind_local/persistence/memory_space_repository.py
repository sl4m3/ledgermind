"""SQLite repository for isolated memory spaces."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now_iso8601_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class MemorySpace:
    """Persistent storage identity for a logical memory boundary."""

    memory_space_id: str
    source_client: str
    display_name: str | None
    created_at: str
    updated_at: str


class MemorySpaceSourceClientChangedError(RuntimeError):
    """Raised when an existing space has a different source_client."""


class SQLiteMemorySpaceRepository:
    """Repository wrapper over the ``memory_spaces`` table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self, memory_space_id: str) -> MemorySpace | None:
        row = self._connection.execute(
            """
            SELECT
                memory_space_id,
                source_client,
                display_name,
                created_at,
                updated_at
            FROM memory_spaces
            WHERE memory_space_id = ?
            """,
            (memory_space_id,),
        ).fetchone()
        if row is None:
            return None

        return MemorySpace(
            memory_space_id=row["memory_space_id"],
            source_client=row["source_client"],
            display_name=row["display_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def ensure(
        self,
        memory_space_id: str,
        source_client: str,
        *,
        display_name: str | None = None,
    ) -> MemorySpace:
        now = _now_iso8601_utc()
        self._connection.execute(
            """
            INSERT OR IGNORE INTO memory_spaces (
                memory_space_id,
                display_name,
                source_client,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                memory_space_id,
                display_name,
                source_client,
                now,
                now,
            ),
        )

        space = self.get(memory_space_id)
        if space is None:
            raise RuntimeError(f"memory space '{memory_space_id}' could not be ensured")
        if space.source_client != source_client:
            raise MemorySpaceSourceClientChangedError(
                f"memory space '{memory_space_id}' has different source_client"
            )
        return space
