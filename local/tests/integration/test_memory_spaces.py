"""Integration tests for memory-space repository guarantees."""

from __future__ import annotations

import sqlite3

import pytest

from ledgermind_local.persistence import (
    MemorySpaceSourceClientChangedError,
    SQLiteMemorySpaceRepository,
    open_sqlite_connection,
)
from ledgermind_local.persistence import rounds_migrations as migrations


def _create_database(path) -> sqlite3.Connection:
    connection = open_sqlite_connection(path)
    try:
        migrations.apply_migrations(connection)
    except sqlite3.DatabaseError:
        connection.close()
        raise
    return connection


def test_memory_space_ensure_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    connection = _create_database(db_path)
    try:
        repo = SQLiteMemorySpaceRepository(connection)
        first = repo.ensure("space-a", "client-a", display_name="Alpha")
        second = repo.ensure("space-a", "client-a", display_name="Alpha")

        assert first.memory_space_id == "space-a"
        assert second.memory_space_id == "space-a"
        count = connection.execute(
            "SELECT COUNT(*) AS total FROM memory_spaces WHERE memory_space_id = ?",
            ("space-a",),
        ).fetchone()[0]
        assert count == 1
    finally:
        connection.close()


def test_memory_spaces_are_isolated_by_id(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    connection = _create_database(db_path)
    try:
        repo = SQLiteMemorySpaceRepository(connection)
        repo.ensure("space-a", "client-a", display_name="Alpha")
        repo.ensure("space-b", "client-b", display_name="Beta")

        space_a = repo.get("space-a")
        space_b = repo.get("space-b")

        assert space_a is not None
        assert space_b is not None
        assert space_a.memory_space_id == "space-a"
        assert space_b.memory_space_id == "space-b"
        assert space_a.source_client == "client-a"
        assert space_b.source_client == "client-b"
        assert space_a.display_name == "Alpha"
        assert space_b.display_name == "Beta"

        rows = connection.execute(
            "SELECT memory_space_id FROM memory_spaces ORDER BY memory_space_id"
        ).fetchall()
        assert [row["memory_space_id"] for row in rows] == ["space-a", "space-b"]
    finally:
        connection.close()


def test_cannot_change_source_client_of_existing_space(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    connection = _create_database(db_path)
    try:
        repo = SQLiteMemorySpaceRepository(connection)
        repo.ensure("space-a", "client-a", display_name="Alpha")

        with pytest.raises(MemorySpaceSourceClientChangedError):
            repo.ensure("space-a", "client-b", display_name="Bravo")
    finally:
        connection.close()
