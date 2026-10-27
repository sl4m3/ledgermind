"""SQLite connection factory for the local LedgerMind service."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_BUSY_TIMEOUT_MS = 5_000


def _open_connection(database_path: str | Path) -> sqlite3.Connection:
    """Open a raw sqlite3 connection without implicit datetime converters."""

    return sqlite3.connect(
        database_path,
        detect_types=0,
        check_same_thread=True,
        timeout=5.0,
    )


def _configure_connection(
    connection: sqlite3.Connection,
    *,
    busy_timeout_ms: int,
) -> None:
    """Apply canonical SQLite pragma set for the local service."""

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # Write-Ahead Logging to allow concurrent read access during write lock boundaries.
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    connection.execute("PRAGMA temp_store = MEMORY")


def open_sqlite_connection(
    database_path: str | Path,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    """Create and fully configure sqlite3 connection."""

    connection = _open_connection(database_path)
    _configure_connection(connection, busy_timeout_ms=busy_timeout_ms)
    return connection


@contextmanager
def managed_connection(
    database_path: str | Path,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> Iterator[sqlite3.Connection]:
    """Yield a configured connection that is always closed after use."""

    connection = open_sqlite_connection(
        database_path,
        busy_timeout_ms=busy_timeout_ms,
    )
    try:
        yield connection
    finally:
        connection.close()
