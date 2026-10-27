from __future__ import annotations

import json
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from ledgermind_integrations.runtime.delivery import DeliveryWorker, RoundSubmitter
from ledgermind_integrations.runtime.spool import FileSpool


class FakeClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def submit_round(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {"status": "accepted"}


def test_delivery_sends_only_request_and_completes(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")
    payload = {
        "schema_version": 2,
        "memory_space_id": "workspace",
        "source": {},
        "round": {},
        "payload_digest": "sha256:" + "a" * 64,
        "idempotency_key": "sha256:" + "a" * 64,
    }
    spool.enqueue_ready(payload["idempotency_key"], payload)
    client = FakeClient()
    worker = DeliveryWorker(spool, client)

    assert worker.run_once() is True
    assert client.payloads == [payload]
    assert spool.stats().ready_delivery == 0


def test_committed_local_receipt_completes_delivery_without_repeating(tmp_path):
    class QueuedClient:
        def submit_round(self, _payload):
            return {"schema_version": 2, "raw_round_id": "stored-1", "status": "queued_for_core"}

    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("capture", {"idempotency_key": "capture"})
    worker = DeliveryWorker(spool, QueuedClient())
    assert worker.run_once()
    assert spool.stats().ready_delivery == 0
    assert not worker.run_once()


def test_delivery_failure_metadata_does_not_include_exception_payload(tmp_path: Path) -> None:
    class FailingClient:
        def submit_round(self, _payload: Mapping[str, Any]) -> dict[str, Any]:
            raise RuntimeError("payload=TOP_SECRET")

    spool = FileSpool(tmp_path / "spool")
    payload = {
        "schema_version": 2,
        "memory_space_id": "workspace",
        "source": {},
        "round": {},
        "payload_digest": "sha256:" + "b" * 64,
        "idempotency_key": "sha256:" + "b" * 64,
    }
    spool.enqueue_ready(payload["idempotency_key"], payload)

    DeliveryWorker(spool, cast(RoundSubmitter, FailingClient())).run_once()

    queued = next(spool.ready_dir.glob("*.json"))
    failed_text = queued.read_text(encoding="utf-8")
    assert "TOP_SECRET" not in failed_text
    assert json.loads(failed_text)["delivery"]["attempts"] == 1
    assert json.loads(failed_text)["delivery"]["last_error_type"] == "RuntimeError"


def test_unconfirmed_round_stays_queued_and_new_round_is_added(tmp_path: Path) -> None:
    class UnconfirmedClient:
        def submit_round(self, _payload: Mapping[str, Any]) -> dict[str, Any]:
            return {}

    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("first", {"idempotency_key": "first"})
    DeliveryWorker(spool, UnconfirmedClient()).run_once()
    spool.enqueue_ready("second", {"idempotency_key": "second"})
    assert sorted(path.name for path in spool.ready_dir.glob("*.json")) == [
        "first.json", "second.json"
    ]
    assert spool.stats().failed == 0


def test_transient_failures_do_not_exhaust_delivery_queue(tmp_path: Path) -> None:
    class FailingClient:
        def submit_round(self, _payload: Mapping[str, Any]) -> dict[str, Any]:
            raise ConnectionError("offline")

    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("first", {"idempotency_key": "first"})
    worker = DeliveryWorker(spool, FailingClient())
    for _ in range(10):
        queued = spool.ready_dir / "first.json"
        data = json.loads(queued.read_text(encoding="utf-8"))
        data["delivery"]["next_attempt_at"] = 0
        spool.retry("first.json", data)
        worker.run_once()
    assert spool.stats().ready_delivery == 1
    assert spool.stats().failed == 0
    assert json.loads(queued.read_text(encoding="utf-8"))["delivery"]["attempts"] == 10


def test_retry_remains_possible_when_queue_reaches_byte_limit(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("first", {"idempotency_key": "first"})
    spool.max_bytes = (spool.ready_dir / "first.json").stat().st_size
    item_name, envelope = spool.pop_ready()[0]
    envelope["delivery"]["attempts"] = 1
    envelope["delivery"]["next_attempt_at"] = 123.0
    spool.retry(item_name, envelope)
    assert spool.stats().ready_delivery == 1
    assert spool.stats().inflight == 0


def test_backoff_on_old_round_does_not_block_new_round(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("a-old", {"idempotency_key": "old"})
    name, envelope = spool.pop_ready(limit=1)[0]
    envelope["delivery"]["next_attempt_at"] = 10**12
    spool.retry(name, envelope)
    spool.enqueue_ready("z-new", {"idempotency_key": "new"})
    claimed = spool.pop_ready(limit=1)
    assert [item[1]["request"]["idempotency_key"] for item in claimed] == ["new"]


def test_spool_delivery_status_is_content_free_and_clearable(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")

    spool.note_delivery_failure("RuntimeError: payload=TOP_SECRET")

    payload = json.loads(spool.delivery_status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pending"
    assert payload["reason"] == "RuntimeError"
    assert "TOP_SECRET" not in spool.delivery_status_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(spool.delivery_status_path.stat().st_mode) == 0o600
    spool.clear_delivery_failure()
    assert not spool.delivery_status_path.exists()


def test_full_spool_can_still_record_failure_diagnostic(tmp_path):
    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("capture", {"idempotency_key": "capture"})
    spool.max_bytes = 1
    spool.note_delivery_failure("SpoolFullError")
    assert json.loads(spool.delivery_status_path.read_text())["reason"] == "SpoolFullError"
