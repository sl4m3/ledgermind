"""Canonical migration runner for Local-owned ``rounds.db``."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import migrations as _shared

MIGRATION_DIR = Path(__file__).resolve().parent / "rounds_migrations"
LOCAL_SCHEMA_VERSION = 14
Migration = _shared.Migration
MigrationError = _shared.MigrationError
MigrationChecksumError = _shared.MigrationChecksumError
MigrationVersionError = _shared.MigrationVersionError
UnknownMigrationError = _shared.UnknownMigrationError


def load_migrations(migration_dir: Path | None = None) -> tuple[Migration, ...]:
    """Return the packaged rounds migrations or an explicit test history."""

    return _shared.load_migrations(migration_dir or MIGRATION_DIR)


def apply_migrations(
    conn: sqlite3.Connection,
    migration_dir: Path | None = None,
) -> tuple[Migration, ...]:
    """Apply the packaged rounds migrations or an explicit migration history."""

    return _shared.apply_migrations(conn, migration_dir or MIGRATION_DIR)
