from __future__ import annotations

import json
import sqlite3
from copy import deepcopy

from fastapi.testclient import TestClient
from ledgermind_protocol import calculate_raw_round_digest

from ledgermind_local.api.app import create_app
from ledgermind_local.api.dependencies import Settings
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations as migrations

_FIXTURE = {
    "schema_version": 2,
    "idempotency_key": "sha256:19dd0368d25bd5888fffe1f5d0a1e7ace48337459dcbd27d325c1030243e7b08",
    "memory_space_id": "workspace_01",
    "source": {
        "system": "hermes",
        "instance_id": "src_hermes_local",
        "profile_id": "default",
        "session_id": "session_01",
        "round_id": "1001:1003",
        "first_event_id": "1001",
        "final_event_id": "1003",
        "event_ids": ["1001", "1002", "1003"],
        "source_schema_version": 1,
        "adapter_version": "hermes-python/0.1.0",
    },
    "round": {
        "started_at": "2026-08-02T20:00:00Z",
        "completed_at": "2026-08-02T20:01:05Z",
        "events": [
            {
                "event_id": "1001",
                "sequence": 0,
                "kind": "message",
                "role": "user",
                "content": [{"type": "text", "text": "request"}],
            },
            {
                "event_id": "1002",
                "sequence": 1,
                "kind": "tool_call",
                "tool_call_id": "call_1",
                "tool_name": "read_file",
                "arguments": {"path": "README.md"},
            },
            {
                "event_id": "1003",
                "sequence": 2,
                "kind": "message",
                "role": "assistant",
                "final": True,
                "content": [{"type": "text", "text": "response"}],
            },
        ],
    },
    "payload_digest": "sha256:19dd0368d25bd5888fffe1f5d0a1e7ace48337459dcbd27d325c1030243e7b08",
}


def _bootstrap(path) -> None:
    connection = open_sqlite_connection(path)
    try:
        migrations.apply_migrations(connection)
        connection.commit()
    finally:
        connection.close()


def _client(path) -> TestClient:
    return TestClient(
        create_app(
            application=object(),
            settings=Settings(database_path=path, api_token="token"),
        )
    )


def test_post_round_queues_raw_round_for_core(tmp_path) -> None:
    database = tmp_path / "state.db"
    _bootstrap(database)

    response = _client(database).post(
        "/rounds",
        headers={"Authorization": "Bearer token"},
        json=_FIXTURE,
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["duplicate"] is False
    assert payload["status"] == "queued_for_core"
    assert payload["core_command_id"]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_rounds").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT transport_status FROM raw_round_core_deliveries"
            ).fetchone()[0]
            == "queued"
        )
        stored = connection.execute("SELECT payload_json FROM raw_rounds").fetchone()[0]
        assert "statement" not in stored


def test_post_round_duplicate_returns_existing_ids(tmp_path) -> None:
    database = tmp_path / "state.db"
    _bootstrap(database)
    client = _client(database)

    first = client.post(
        "/rounds", headers={"Authorization": "Bearer token"}, json=_FIXTURE
    )
    second = client.post(
        "/rounds", headers={"Authorization": "Bearer token"}, json=_FIXTURE
    )

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["raw_round_id"] == first.json()["raw_round_id"]


def test_post_round_same_source_different_payload_is_conflict(tmp_path) -> None:
    database = tmp_path / "state.db"
    _bootstrap(database)
    client = _client(database)
    assert (
        client.post(
            "/rounds", headers={"Authorization": "Bearer token"}, json=_FIXTURE
        ).status_code
        == 202
    )

    changed = deepcopy(_FIXTURE)
    changed["round"]["events"][1]["arguments"]["path"] = "different.md"
    changed["payload_digest"] = calculate_raw_round_digest(changed)
    changed["idempotency_key"] = changed["payload_digest"]
    response = client.post(
        "/rounds", headers={"Authorization": "Bearer token"}, json=changed
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "source_round_conflict"


def test_post_round_same_source_isolated_by_memory_space(tmp_path) -> None:
    database = tmp_path / "state.db"
    _bootstrap(database)
    client = _client(database)
    second = json.loads(json.dumps(_FIXTURE))
    second["memory_space_id"] = "workspace_02"

    first_response = client.post(
        "/rounds", headers={"Authorization": "Bearer token"}, json=_FIXTURE
    )
    second_response = client.post(
        "/rounds", headers={"Authorization": "Bearer token"}, json=second
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_rounds").fetchone()[0] == 2
