from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ledgermind_protocol import RawRoundRequest, calculate_raw_round_digest

from ledgermind_local.persistence import (
    SQLiteUnitOfWork,
    open_sqlite_connection,
)
from ledgermind_local.persistence import rounds_migrations as migrations
from ledgermind_local.persistence.raw_round_repository import SQLiteRawRoundRepository
from ledgermind_local.raw_rounds import RawRoundIngestHandler
from ledgermind_local.scheduler.retention_worker import RawRoundRetentionWorker

_FIXTURE = {
    "schema_version": 2,
    "idempotency_key": "sha256:" + "a" * 64,
    "memory_space_id": "retention-space",
    "source": {
        "system": "hermes",
        "instance_id": "instance",
        "profile_id": "profile",
        "session_id": "session",
        "round_id": "round",
        "first_event_id": "event-1",
        "final_event_id": "event-2",
        "event_ids": ["event-1", "event-2"],
        "source_schema_version": 1,
        "adapter_version": "test/1",
    },
    "round": {
        "started_at": "2026-08-02T20:00:00Z",
        "completed_at": "2026-08-02T20:01:00Z",
        "events": [
            {
                "event_id": "event-1",
                "sequence": 0,
                "kind": "message",
                "role": "user",
                "content": [{"type": "text", "text": "request"}],
            },
            {
                "event_id": "event-2",
                "sequence": 1,
                "kind": "message",
                "role": "assistant",
                "final": True,
                "content": [{"type": "text", "text": "response"}],
            },
        ],
    },
    "payload_digest": "sha256:" + "0" * 64,
}
_FIXTURE["payload_digest"] = calculate_raw_round_digest(_FIXTURE)
_FIXTURE["idempotency_key"] = _FIXTURE["payload_digest"]


def _bootstrap(path: Path) -> None:
    connection = open_sqlite_connection(path)
    try:
        migrations.apply_migrations(connection)
        connection.commit()
    finally:
        connection.close()


def _insert_expired_payloads(path: Path, count: int = 2) -> list[str]:
    connection = open_sqlite_connection(path)
    try:
        connection.execute(
            """
            INSERT INTO memory_spaces (
                memory_space_id, display_name, source_client, created_at, updated_at
            ) VALUES ('worker-space', 'Worker', 'test', '2026-01-01T00:00:00+00:00',
                      '2026-01-01T00:00:00+00:00')
            """
        )
        repository = SQLiteRawRoundRepository(connection)
        raw_round_ids: list[str] = []
        for index in range(count):
            raw_round_id = f"worker-round-{index}"
            raw_round_ids.append(raw_round_id)
            repository.insert(
                raw_round_id=raw_round_id,
                memory_space_id="worker-space",
                source_system="test",
                source_instance_id="instance",
                source_profile_id="profile",
                source_session_id=f"session-{index}",
                source_round_id=f"round-{index}",
                source_round_key=f"source-key-{index}",
                capture_schema_version=1,
                adapter_version="test/1",
                payload_json=f'{{"index":{index}}}',
                payload_digest="sha256:" + str(index + 1) * 64,
                started_at="2026-01-01T00:00:00+00:00",
                completed_at="2026-01-01T00:01:00+00:00",
                retention_expires_at="2020-01-01T00:00:00+00:00",
            )
        connection.commit()
        return raw_round_ids
    finally:
        connection.close()


def test_expired_raw_round_payload_is_purged_but_metadata_remains(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.db"
    _bootstrap(database)
    request = RawRoundRequest.model_validate(_FIXTURE)
    result = RawRoundIngestHandler(database_path=database, retention_days=1).handle(
        request
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE raw_round_payloads SET retention_expires_at = ? WHERE raw_round_id = ?",
            ("2020-01-01T00:00:00+00:00", result.raw_round_id),
        )
        connection.commit()

    with SQLiteUnitOfWork(database, write_transaction=True) as uow:
        purged = uow.raw_rounds.purge_expired(now="2021-01-01T00:00:00+00:00")
        uow.commit()

    assert purged == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_rounds").fetchone()[0] == 1
        payload = connection.execute(
            "SELECT payload_json, payload_bytes, deleted_at FROM raw_round_payloads WHERE raw_round_id = ?",
            (result.raw_round_id,),
        ).fetchone()
        assert payload[0] == "{}"
        assert payload[1] == 0
        assert payload[2] is not None


def test_retention_worker_process_once_is_idempotent_and_respects_limit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "worker.db"
    _bootstrap(database)
    raw_round_ids = _insert_expired_payloads(database)
    worker = RawRoundRetentionWorker(database)

    first = worker.process_once(now="2021-01-01T00:00:00+00:00", limit=1)
    second = worker.process_once(now="2021-01-01T00:00:00+00:00", limit=1)
    third = worker.process_once(now="2021-01-01T00:00:00+00:00", limit=1)

    assert first.purged == 1
    assert second.purged == 1
    assert third.purged == 0
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT raw_round_id, payload_json, payload_bytes, deleted_at
            FROM raw_round_payloads
            ORDER BY raw_round_id
            """
        ).fetchall()
        assert [row[0] for row in rows] == sorted(raw_round_ids)
        assert all(row[1] == "{}" and row[2] == 0 and row[3] for row in rows)


def test_retention_worker_rolls_back_all_payload_updates_on_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "worker-rollback.db"
    _bootstrap(database)
    raw_round_ids = _insert_expired_payloads(database)

    def fail_after_one_delete(
        repository: SQLiteRawRoundRepository,
        *,
        now: str | None = None,
        limit: int = 100,
    ) -> int:
        del limit
        repository._connection.execute(
            """
            UPDATE raw_round_payloads
            SET payload_json = '{}', payload_bytes = 0, deleted_at = ?
            WHERE raw_round_id = ?
            """,
            (now, raw_round_ids[0]),
        )
        raise sqlite3.OperationalError("injected sqlite failure")

    monkeypatch.setattr(
        SQLiteRawRoundRepository,
        "purge_expired",
        fail_after_one_delete,
    )

    with pytest.raises(sqlite3.OperationalError, match="injected sqlite failure"):
        RawRoundRetentionWorker(database).process_once(
            now="2021-01-01T00:00:00+00:00",
            limit=2,
        )

    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT payload_json, payload_bytes, deleted_at
            FROM raw_round_payloads
            ORDER BY raw_round_id
            """
        ).fetchall()
        assert rows == [(f'{{"index":{index}}}', len(f'{{"index":{index}}}'), None) for index in range(2)]
