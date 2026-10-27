from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ledgermind_integrations.adapters.hermes.round_capture import build_raw_round
from ledgermind_integrations.runtime.spool import FileSpool
from ledgermind_integrations.runtime.spool_migration import migrate_spool


def _raw_round() -> dict[str, Any]:
    return build_raw_round(
        memory_space_id="workspace",
        source_system="hermes",
        source_instance_id="instance",
        profile_id="profile",
        session_id="session",
        round_id="round",
        started_at="2026-08-02T20:00:00Z",
        completed_at="2026-08-02T20:01:00Z",
        events=[
            {"event_id": "user", "kind": "message", "role": "user", "content": "question"},
            {
                "event_id": "assistant",
                "kind": "message",
                "role": "assistant",
                "content": "answer",
                "final": True,
            },
        ],
    )


def _historical_round() -> dict[str, Any]:
    payload = _raw_round()
    payload.pop("schema_version")
    payload["api_version"] = "2"
    payload["extensions"] = {
        "ledgermind_context_v1": {
            "retrieval_request_id": "retrieval-1",
            "delivered_value_ids": ["value-1"],
            "content": "full prior context must not survive migration",
        }
    }
    return payload


def _read(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_migration_recovers_and_rewrites_every_delivery_queue(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")
    historical = _historical_round()
    source = historical["source"]

    spool.enqueue_pending(
        "pending-round",
        {
            "api_version": "2",
            "session_id": "session",
            "round_id": "round",
            "extensions": historical["extensions"],
        },
    )
    spool.enqueue_ready("ready-round", historical)
    spool.enqueue_ready("inflight-round", historical)
    spool.pop_ready()
    failed = spool.failed_dir / "retryable.json"
    failed.write_text(
        json.dumps(
            {
                "request": historical,
                "delivery": {"attempts": 2, "retryable": True},
            }
        ),
        encoding="utf-8",
    )

    result = migrate_spool(spool)

    assert result.recovered_inflight == 2
    assert result.migrated_pending == 1
    assert result.migrated_failed == 1
    assert result.promoted_failed == 1
    assert not list(spool.inflight_dir.glob("*.json"))
    assert not list(spool.failed_dir.glob("*.json"))

    pending = _read(next(spool.pending_dir.glob("*.json")))
    assert pending["schema_version"] == 2
    assert pending["extensions"]["ledgermind_context"] == {
        "schema_version": 1,
        "retrieval_request_id": "retrieval-1",
        "delivered_value_ids": ["value-1"],
    }
    for path in spool.ready_dir.glob("*.json"):
        envelope = _read(path)
        request = envelope["request"]
        assert request["schema_version"] == 2
        assert request["source"] == source
        assert request["idempotency_key"] == request["payload_digest"]
        assert request["extensions"]["ledgermind_context"] == {
            "schema_version": 1,
            "retrieval_request_id": "retrieval-1",
            "delivered_value_ids": ["value-1"],
        }

    second = migrate_spool(spool)
    assert second == result.__class__()


def test_migration_recomputes_digest_without_changing_source_identity(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")
    payload = _raw_round()
    source = payload["source"]
    payload["payload_digest"] = "sha256:" + "0" * 64
    payload["idempotency_key"] = payload["payload_digest"]
    spool.enqueue_ready("digest-round", payload)

    result = migrate_spool(spool)

    assert result.migrated_ready == 1
    migrated = _read(next(spool.ready_dir.glob("*.json")))["request"]
    assert migrated["source"] == source
    assert migrated["payload_digest"] != "sha256:" + "0" * 64
    assert migrated["idempotency_key"] == migrated["payload_digest"]
