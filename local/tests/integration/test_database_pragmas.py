"""Integration tests for SQLite connection configuration."""

import sqlite3
from datetime import datetime
from pathlib import Path

from ledgermind_local.persistence.database import (
    managed_connection,
    open_sqlite_connection,
)


def _pragma_value(conn: sqlite3.Connection, pragma: str) -> str | int:
    row = conn.execute(pragma).fetchone()
    if row is None:
        raise AssertionError(f"pragma '{pragma}' returned no row")
    return row[0]


def test_open_sqlite_connection_configures_pragmas(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    with managed_connection(db_path) as conn:
        assert _pragma_value(conn, "PRAGMA foreign_keys") == 1
        assert _pragma_value(conn, "PRAGMA journal_mode") == "wal"
        assert int(_pragma_value(conn, "PRAGMA synchronous")) == 2
        assert int(_pragma_value(conn, "PRAGMA busy_timeout")) == 5000
        assert int(_pragma_value(conn, "PRAGMA temp_store")) == 2
        assert conn.row_factory is sqlite3.Row


def test_managed_connection_is_closed_after_context_exit(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    with managed_connection(db_path) as conn:
        conn.execute("SELECT 1")

    try:
        conn.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return
    else:  # pragma: no cover - defensive
        raise AssertionError("connection expected to be closed")


def test_timestamps_are_read_explicitly_as_strings(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    conn = open_sqlite_connection(db_path)
    try:
        conn.execute(
            "CREATE TABLE sample (id INTEGER PRIMARY KEY, emitted_at DATETIME)"
        )
        stamp = datetime.fromisoformat("2026-08-01T12:34:56")
        conn.execute("INSERT INTO sample (emitted_at) VALUES (?)", (stamp.isoformat(),))
        conn.commit()

        row = conn.execute("SELECT emitted_at FROM sample").fetchone()
        assert isinstance(row["emitted_at"], str)
    finally:
        conn.close()
