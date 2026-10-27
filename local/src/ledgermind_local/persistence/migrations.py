"""SQLite migration loader and applier for the local service."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MIGRATION_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_FILE_RE = re.compile(r"^(?P<version>\d{4})_.*\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    """Concrete migration payload."""

    version: int
    name: str
    checksum: str
    sql: str


class MigrationError(RuntimeError):
    """Base class for migration application errors."""


class MigrationVersionError(MigrationError):
    """Database migration history diverges from available migration set."""


class MigrationChecksumError(MigrationError):
    """Applied migration checksum differs from packaged migration content."""


class UnknownMigrationError(MigrationError):
    """Database already contains an unknown migration version."""


def _migration_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _read_file_text(entry: Path) -> str:
    return entry.read_text(encoding="utf-8")


def _discover_migrations(migration_dir: Path = MIGRATION_DIR) -> tuple[Migration, ...]:
    if not migration_dir.is_dir():
        return ()

    migrations: list[Migration] = []
    for entry in migration_dir.iterdir():
        name = entry.name
        match = _MIGRATION_FILE_RE.fullmatch(name)
        if not match or not entry.is_file():
            continue

        version = int(match.group("version"))
        sql = _read_file_text(entry)
        migrations.append(
            Migration(
                version=version,
                name=name,
                checksum=_migration_checksum(sql),
                sql=sql,
            )
        )

    return tuple(sorted(migrations, key=lambda migration: migration.version))


def load_migrations(migration_dir: Path = MIGRATION_DIR) -> tuple[Migration, ...]:
    """Return packaged migrations sorted by version."""

    loaded = _discover_migrations(migration_dir)
    versions = [migration.version for migration in loaded]
    if len(set(versions)) != len(versions):
        duplicates = sorted(
            version for version in set(versions) if versions.count(version) > 1
        )
        raise MigrationError(f"duplicate migration versions detected: {duplicates}")

    return loaded


def _schema_migrations_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'schema_migrations'
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def _load_applied_versions(conn: sqlite3.Connection) -> dict[int, str]:
    if not _schema_migrations_table_exists(conn):
        return {}

    rows = conn.execute(
        """
        SELECT version, checksum
        FROM schema_migrations
        ORDER BY version
        """
    ).fetchall()
    return {int(row[0]): row[1] for row in rows}


def _validate_applied_state(
    conn: sqlite3.Connection,
    migrations: tuple[Migration, ...],
) -> int:
    applied = _load_applied_versions(conn)
    if not applied:
        return 0

    available = {migration.version: migration for migration in migrations}
    available_versions = tuple(sorted(available))
    if not available_versions:
        raise UnknownMigrationError(
            "database contains migration history but package has no migrations"
        )

    applied_versions = tuple(sorted(applied))
    latest_available = available_versions[-1]

    unknown = sorted(
        version for version in applied_versions if version not in available
    )
    if unknown:
        max_unknown = unknown[-1]
        if max_unknown > latest_available:
            raise UnknownMigrationError(
                f"database already has unknown migration version {max_unknown}"
            )
        raise MigrationVersionError(f"unknown migration version in database: {unknown}")

    expected_prefix = tuple(
        version for version in available_versions if version <= max(applied_versions)
    )
    if applied_versions != expected_prefix:
        raise MigrationVersionError(
            f"database migration history is not a contiguous prefix: {applied_versions}"
        )

    for version in applied_versions:
        migration = available[version]
        if applied[version] != migration.checksum:
            raise MigrationChecksumError(
                f"checksum mismatch for migration {migration.name}"
            )

    return applied_versions[-1]


def _applied_at_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _apply_single_migration(
    conn: sqlite3.Connection,
    migration: Migration,
) -> None:
    owns_transaction = False
    restore_foreign_keys = False
    try:
        # SQLite cannot change a CHECK constraint while a transaction is
        # active. Migration 0014 rebuilds a parent table referenced by
        # profile-slot and capability tables, so temporarily disable FK
        # enforcement before BEGIN and restore it only after COMMIT.
        if migration.sql.lstrip().startswith("PRAGMA foreign_keys = OFF"):
            foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()
            restore_foreign_keys = bool(foreign_keys and foreign_keys[0])
            if restore_foreign_keys:
                conn.execute("PRAGMA foreign_keys = OFF")
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
            owns_transaction = True
        for statement in migration.sql.split(";"):
            if statement.strip():
                conn.execute(statement)
        conn.execute(
            """
            INSERT INTO schema_migrations (version, name, checksum, applied_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                migration.version,
                migration.name,
                migration.checksum,
                _applied_at_timestamp(),
            ),
        )
        if owns_transaction:
            conn.commit()
        if restore_foreign_keys:
            conn.execute("PRAGMA foreign_keys = ON")
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        if restore_foreign_keys:
            conn.execute("PRAGMA foreign_keys = ON")
        raise


def apply_migrations(
    conn: sqlite3.Connection,
    migration_dir: Path = MIGRATION_DIR,
) -> tuple[Migration, ...]:
    """Apply pending migrations to ``conn`` and return applied migrations."""

    migrations = (
        load_migrations()
        if migration_dir == MIGRATION_DIR
        else load_migrations(migration_dir)
    )
    current = _validate_applied_state(conn, migrations)
    pending = [m for m in migrations if m.version > current]
    applied: list[Migration] = []

    for migration in pending:
        _apply_single_migration(conn, migration)
        applied.append(migration)

    return tuple(applied)
