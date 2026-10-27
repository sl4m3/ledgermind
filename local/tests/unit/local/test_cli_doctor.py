"""Tests for the Local `doctor` command."""

from __future__ import annotations

from pathlib import Path

from ledgermind_local.cli import main
from ledgermind_local.persistence import SQLiteUnitOfWork, rounds_migrations


def _build_rounds_database(path: Path) -> None:
    with SQLiteUnitOfWork(path) as uow:
        rounds_migrations.apply_migrations(uow.connection)
        uow.memory_spaces.ensure("space-a", "hermes")
        uow.commit()


def test_doctor_returns_success_for_clean_rounds_database(tmp_path: Path) -> None:
    db_path = tmp_path / "rounds.db"
    _build_rounds_database(db_path)

    assert main(["doctor", "--database", str(db_path)]) == 0
