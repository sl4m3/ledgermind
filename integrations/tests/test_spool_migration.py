from __future__ import annotations

import json
import os
import time
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
    # A tiny TTL lets the freshly claimed in-flight records expire so this
    # exercises the full recovery path regardless of claim age.
    spool = FileSpool(tmp_path / "spool", inflight_ttl_seconds=0.1)
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
    time.sleep(0.2)  # let both in-flight claims exceed the 0.1s TTL
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


def test_migration_does_not_steal_live_inflight_claim(tmp_path: Path) -> None:
    # A fresh in-flight record belongs to a live worker/drain. migrate_spool must
    # leave it in inflight/ (the owner will complete or retry it), otherwise a
    # concurrent drain would re-queue and re-send a round that is already being
    # delivered. Only records older than the TTL are recovered.
    spool = FileSpool(tmp_path / "spool", inflight_ttl_seconds=300.0)
    spool.enqueue_ready("live", _raw_round())
    spool.pop_ready()  # moves the record to inflight/ with a fresh claimed_at

    assert spool.stats().inflight == 1
    result = migrate_spool(spool)

    assert result.recovered_inflight == 0
    assert spool.stats().inflight == 1
    assert spool.stats().ready_delivery == 0


def test_migration_recovers_expired_inflight_claim(tmp_path: Path) -> None:
    # Once the claim is older than the TTL the worker is presumed dead, so the
    # record must return to ready/ for another drain to pick up.
    spool = FileSpool(tmp_path / "spool", inflight_ttl_seconds=0.1)
    spool.enqueue_ready("stale", _raw_round())
    spool.pop_ready()
    time.sleep(0.2)  # age the claim past the TTL

    result = migrate_spool(spool)

    assert result.recovered_inflight == 1
    assert spool.stats().inflight == 0
    assert spool.stats().ready_delivery == 1
    recovered = _read(next(spool.ready_dir.glob("*.json")))
    assert "claimed_at" not in recovered["delivery"]
    assert "worker_id" not in recovered["delivery"]

def test_migration_does_not_steal_claim_without_claimed_at(tmp_path: Path) -> None:
    # pop_ready renames ready/->inflight/ first and only then rewrites the record
    # with claimed_at, while rename() keeps mtime. A record without claimed_at is
    # therefore being claimed right now, not abandoned: recovering it would queue
    # a duplicate round for delivery.
    spool = FileSpool(tmp_path / "spool", inflight_ttl_seconds=0.1)
    spool.enqueue_ready("round-1", _raw_round())
    spool.pop_ready()
    inflight = spool.inflight_dir / "round-1.json"
    payload = _read(inflight)
    payload["delivery"].pop("claimed_at")
    inflight.write_text(json.dumps(payload), encoding="utf-8")
    old = time.time() - 3_600
    os.utime(inflight, (old, old))  # mtime is not evidence of claim age

    result = migrate_spool(spool)

    assert result.recovered_inflight == 0
    assert inflight.exists()
    assert spool.stats().ready_delivery == 0
    assert spool.stats().inflight == 1


def test_failed_promotion_stops_after_attempt_ceiling(tmp_path: Path) -> None:
    # A permanent 4xx never becomes valid by retrying, so an exhausted record
    # must stay in failed/ instead of bouncing between ready/ and failed/.
    spool = FileSpool(tmp_path / "spool", retryable_failed_max_attempts=2)
    spool._ensure()
    failed = spool.failed_dir / "exhausted.json"
    failed.write_text(
        json.dumps(
            {
                "request": _raw_round(),
                "delivery": {"attempts": 2, "retryable": True},
            }
        ),
        encoding="utf-8",
    )

    result = migrate_spool(spool)

    assert result.promoted_failed == 0
    assert result.retired_failed == 1
    assert spool.stats().ready_delivery == 0
    assert failed.exists()
    delivery = _read(failed)["delivery"]
    assert delivery["retryable"] is False
    assert delivery["retirement_reason"] == "retryable_failed_attempts_exhausted"
    assert delivery["retired_at"]

    second = migrate_spool(spool)
    assert second.retired_failed == 0
    assert second.promoted_failed == 0
    assert failed.exists()


def test_failed_promotion_stops_after_age_ceiling(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", retryable_failed_max_age_seconds=1.0)
    spool._ensure()
    failed = spool.failed_dir / "stale.json"
    failed.write_text(
        json.dumps(
            {
                "request": _raw_round(),
                "delivery": {
                    "attempts": 0,
                    "retryable": True,
                    "failed_at": time.time() - 10,
                },
            }
        ),
        encoding="utf-8",
    )

    result = migrate_spool(spool)

    assert result.promoted_failed == 0
    assert result.retired_failed == 1
    assert failed.exists()
    delivery = _read(failed)["delivery"]
    assert delivery["retryable"] is False
    assert "age" in delivery["retirement_reason"]


def test_failed_promotion_within_limits_still_promotes(tmp_path: Path) -> None:
    # The ceiling must not swallow a record that is still worth one more try.
    spool = FileSpool(tmp_path / "spool")
    spool._ensure()
    failed = spool.failed_dir / "fixable.json"
    failed.write_text(
        json.dumps(
            {
                "request": _raw_round(),
                "delivery": {"attempts": 1, "retryable": True, "failed_at": time.time()},
            }
        ),
        encoding="utf-8",
    )

    result = migrate_spool(spool)

    assert result.promoted_failed == 1
    assert result.retired_failed == 0
    assert spool.stats().failed == 0
    promoted = _read(spool.ready_dir / "fixable.json")["delivery"]
    assert "failed_at" not in promoted
    assert "failure_reason" not in promoted
