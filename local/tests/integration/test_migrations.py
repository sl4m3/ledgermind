"""Integration tests for SQLite migrations."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

from ledgermind_local.persistence import rounds_migrations as migrations


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_apply_migrations_is_idempotent(tmp_path):
    db_path = tmp_path / "state.db"
    conn = _connect(db_path)
    try:
        first = migrations.apply_migrations(conn)
        second = migrations.apply_migrations(conn)

        rows = conn.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        expected = migrations.load_migrations()

        assert len(first) == len(expected)
        assert second == ()
        assert len(rows) == len(expected)
        for row, migration in zip(rows, expected, strict=True):
            assert row["version"] == migration.version
            assert row["name"] == migration.name
            assert row["checksum"] == migration.checksum
    finally:
        conn.close()


def test_modified_migration_is_detected(tmp_path):
    db_path = tmp_path / "state.db"
    conn = _connect(db_path)
    try:
        migrations.apply_migrations(conn)
        conn.execute("UPDATE schema_migrations SET checksum = '0000' WHERE version = 1")
        conn.commit()

        with pytest.raises(migrations.MigrationChecksumError):
            migrations.apply_migrations(conn)
    finally:
        conn.close()


def test_newer_schema_version_is_blocked(tmp_path):
    db_path = tmp_path / "state.db"
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        latest = max(migration.version for migration in migrations.load_migrations())
        conn.execute(
            """
            INSERT INTO schema_migrations
                (version, name, checksum, applied_at)
            VALUES
                (?, ?, ?, ?)
            """,
            (
                latest + 1,
                "future.sql",
                hashlib.sha256(b"future").hexdigest(),
                "2020-01-01T00:00:00Z",
            ),
        )
        conn.commit()

        with pytest.raises(migrations.UnknownMigrationError):
            migrations.apply_migrations(conn)
    finally:
        conn.close()


def test_failed_migration_is_rolled_back(tmp_path, monkeypatch):
    fake_sql = "CREATE TABLE should_not_exist(id INTEGER PRIMARY KEY);BROKEN SQL;"
    bad_migration = migrations.Migration(
        version=1,
        name="0001_bad.sql",
        checksum=hashlib.sha256(fake_sql.encode("utf-8")).hexdigest(),
        sql=fake_sql,
    )
    monkeypatch.setattr(
        migrations._shared,
        "load_migrations",
        lambda _migration_dir: (bad_migration,),
    )

    conn = _connect(tmp_path / "state.db")
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrations.apply_migrations(conn)

        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='should_not_exist'"
        ).fetchone()
        assert table is None
        migrations_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        assert migrations_table is None
    finally:
        conn.close()
