"""Integration tests for Local-owned SQLite integrity diagnostics."""

from __future__ import annotations

from pathlib import Path

from ledgermind_local.diagnostics.integrity import run_database_integrity_checks
from ledgermind_local.persistence import (
    SQLiteUnitOfWork,
    open_sqlite_connection,
    rounds_migrations,
)


def test_integrity_passes_for_clean_rounds_database(tmp_path: Path) -> None:
    db_path = tmp_path / "rounds.db"
    with SQLiteUnitOfWork(db_path) as uow:
        rounds_migrations.apply_migrations(uow.connection)
        uow.memory_spaces.ensure("space-a", "hermes")
        uow.commit()

    connection = open_sqlite_connection(db_path)
    try:
        assert run_database_integrity_checks(connection) == []
    finally:
        connection.close()