from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from ledgermind_protocol import calculate_payload_digest

from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations as migrations
from ledgermind_local.persistence.contract_migration import (
    CONTRACT_MIGRATION_MARKER,
    ContractMigrationPreconditionError,
    migrate_contract_payloads,
)
from ledgermind_local.persistence.raw_round_repository import SQLiteRawRoundRepository


def _legacy_payload() -> dict[str, object]:
    return {
        "api_version": "2",
        "idempotency_key": "sha256:" + "b" * 64,
        "memory_space_id": "space-1",
        "source": {
            "system": "hermes",
            "instance_id": "instance-1",
            "profile_id": "profile-1",
            "session_id": "session-1",
            "round_id": "round-1",
            "event_ids": ["event-1"],
            "source_schema_version": 1,
            "adapter_version": "adapter",
        },
        "round": {
            "started_at": "2026-08-08T00:00:00Z",
            "completed_at": "2026-08-08T00:01:00Z",
            "events": [
                {
                    "event_id": "event-1",
                    "sequence": 0,
                    "kind": "message",
                    "role": "user",
                    "content": [{"type": "text", "text": "hello"}],
                }
            ],
        },
        "extensions": {
            "ledgermind_context_v1": {
                "retrieval_request_id": "retrieval-1",
                "delivered_value_ids": ["value-1"],
            }
        },
    }


def _json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _seed(path: Path) -> tuple[sqlite3.Connection, dict[str, object]]:
    connection = open_sqlite_connection(path)
    migrations.apply_migrations(connection)
    connection.execute(
        """
        INSERT INTO memory_spaces (
            memory_space_id, source_client, created_at, updated_at
        ) VALUES ('space-1', 'tests', '2026-08-08T00:00:00Z', '2026-08-08T00:00:00Z')
        """
    )
    payload = _legacy_payload()
    serialized = _json(payload)
    repository = SQLiteRawRoundRepository(connection)
    repository.insert(
        raw_round_id="raw-1",
        memory_space_id="space-1",
        source_system="hermes",
        source_instance_id="instance-1",
        source_profile_id="profile-1",
        source_session_id="session-1",
        source_round_id="round-1",
        source_round_key="source-key-1",
        capture_schema_version=1,
        adapter_version="adapter",
        payload_json=serialized,
        payload_digest="sha256:" + "a" * 64,
        started_at="2026-08-08T00:00:00Z",
        completed_at="2026-08-08T00:01:00Z",
    )
    repository.create_core_command(
        command_id="command-1",
        command_type="ingest_raw_round_v2",
        memory_space_id="space-1",
        idempotency_key="sha256:" + "c" * 64,
        payload_json='{"raw_round_id":"raw-1"}',
        payload_digest="sha256:" + "d" * 64,
    )
    repository.create_core_raw_round_delivery(
        raw_round_id="raw-1",
        memory_space_id="space-1",
        command_id="command-1",
        idempotency_key="sha256:" + "c" * 64,
    )
    connection.commit()
    return connection, payload


def test_contract_migration_rewrites_payload_and_transport_metadata(tmp_path: Path) -> None:
    database = tmp_path / "rounds.db"
    connection, _legacy = _seed(database)
    stopped: list[str] = []
    backup = tmp_path / "before-contract-cutover.db"
    try:
        result = migrate_contract_payloads(
            database_path=database,
            connection=connection,
            backup_path=backup,
            stop_delivery=lambda: stopped.append("stopped"),
        )

        assert result.already_applied is False
        assert result.migrated_rounds == 1
        assert result.migrated_commands == 1
        assert result.backup_path == backup
        assert stopped == ["stopped"]
        assert backup.is_file()

        payload_text = connection.execute(
            "SELECT payload_json FROM raw_round_payloads WHERE raw_round_id = 'raw-1'"
        ).fetchone()[0]
        payload = json.loads(payload_text)
        assert payload["schema_version"] == 2
        assert "api_version" not in payload
        assert "ledgermind_context_v1" not in payload["extensions"]
        assert payload["extensions"]["ledgermind_context"]["schema_version"] == 1
        expected_digest = calculate_payload_digest(payload)
        assert connection.execute(
            "SELECT payload_digest FROM raw_rounds WHERE raw_round_id = 'raw-1'"
        ).fetchone()[0] == expected_digest
        assert tuple(
            connection.execute(
                "SELECT command_type, idempotency_key FROM core_commands"
            ).fetchone()
        ) == ("ingest_raw_round", expected_digest)
        assert tuple(
            connection.execute(
                "SELECT idempotency_key, transport_status FROM raw_round_core_deliveries"
            ).fetchone()
        ) == (expected_digest, "queued")
        assert connection.execute(
            "SELECT marker FROM contract_migration_markers WHERE marker = ?",
            (CONTRACT_MIGRATION_MARKER,),
        ).fetchone() is not None
    finally:
        connection.close()


def test_contract_migration_is_idempotent_after_marker(tmp_path: Path) -> None:
    database = tmp_path / "rounds.db"
    connection, _legacy = _seed(database)
    backup = tmp_path / "before-contract-cutover.db"
    try:
        first = migrate_contract_payloads(
            database_path=database,
            connection=connection,
            backup_path=backup,
            stop_delivery=lambda: None,
        )
        second = migrate_contract_payloads(
            database_path=database,
            connection=connection,
            backup_path=backup,
            stop_delivery=lambda: (_ for _ in ()).throw(AssertionError("must not stop")),
        )
        assert first.already_applied is False
        assert second.already_applied is True
        assert second.migrated_rounds == 0
        assert second.migrated_commands == 0
    finally:
        connection.close()


def test_contract_migration_requires_delivery_to_be_stopped(tmp_path: Path) -> None:
    database = tmp_path / "rounds.db"
    connection, _legacy = _seed(database)
    backup = tmp_path / "before-contract-cutover.db"
    try:
        connection.execute("UPDATE core_commands SET status = 'delivering'")
        connection.commit()
        with pytest.raises(ContractMigrationPreconditionError, match="leased command"):
            migrate_contract_payloads(
                database_path=database,
                connection=connection,
                backup_path=backup,
                stop_delivery=lambda: None,
            )
        assert connection.execute(
            "SELECT marker FROM contract_migration_markers WHERE marker = ?",
            (CONTRACT_MIGRATION_MARKER,),
        ).fetchone() is None
        assert connection.execute(
            "SELECT command_type FROM core_commands"
        ).fetchone()[0] == "ingest_raw_round_v2"
    finally:
        connection.close()


def test_contract_migration_backup_is_a_valid_sqlite_snapshot(tmp_path: Path) -> None:
    database = tmp_path / "rounds.db"
    connection, _legacy = _seed(database)
    backup = tmp_path / "before-contract-cutover.db"
    try:
        migrate_contract_payloads(
            database_path=database,
            connection=connection,
            backup_path=backup,
        )
    finally:
        connection.close()
    with sqlite3.connect(backup) as snapshot:
        assert snapshot.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert snapshot.execute(
            "SELECT command_type FROM core_commands"
        ).fetchone()[0] == "ingest_raw_round_v2"


def test_command_digest_is_recomputed_from_canonical_metadata(tmp_path: Path) -> None:
    database = tmp_path / "rounds.db"
    connection, _legacy = _seed(database)
    try:
        migrate_contract_payloads(database_path=database, connection=connection)
        expected = "sha256:" + hashlib.sha256(b'{"raw_round_id":"raw-1"}').hexdigest()
        assert connection.execute(
            "SELECT payload_digest FROM core_commands"
        ).fetchone()[0] == expected
    finally:
        connection.close()
