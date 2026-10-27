from __future__ import annotations

import sqlite3

from ledgermind_local.persistence import rounds_migrations as migrations


def test_inference_profile_migration_creates_profile_binding_and_audit_tables(
    tmp_path,
) -> None:
    connection = sqlite3.connect(tmp_path / "local.db")
    try:
        migrations.apply_migrations(connection)

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "inference_profiles",
            "memory_space_inference_profiles",
            "egress_audit",
        }.issubset(tables)
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(inference_profiles)"
            ).fetchall()
        }
        assert {
            "profile_id",
            "provider_kind",
            "secret_ref",
            "extra_body_json",
            "enabled",
        }.issubset(
            columns
        )
        assert "secret_value" not in columns
    finally:
        connection.close()
