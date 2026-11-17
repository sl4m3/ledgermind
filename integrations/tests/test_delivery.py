from __future__ import annotations

import json
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from ledgermind_integrations.runtime.client import (
    LedgerMindConflictError,
    LedgerMindNetworkError,
    LedgerMindPermanentError,
)
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


def test_server_5xx_retries_forever_until_confirmed(tmp_path: Path) -> None:
    """Transient core (5xx) retries without a ceiling; the round never quarantines."""

    class DownCoreClient:
        def submit_round(self, _payload: Mapping[str, Any]) -> dict[str, Any]:
            raise LedgerMindNetworkError("server returned 503")

    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("first", {"idempotency_key": "first"})
    worker = DeliveryWorker(spool, DownCoreClient())
    for _ in range(10):
        queued = spool.ready_dir / "first.json"
        data = json.loads(queued.read_text(encoding="utf-8"))
        data["delivery"]["next_attempt_at"] = 0
        spool.retry("first.json", data)
        worker.run_once()
    assert spool.stats().ready_delivery == 1
    assert spool.stats().failed == 0
    assert json.loads(queued.read_text(encoding="utf-8"))["delivery"]["attempts"] == 10


def test_permanent_4xx_failure_is_quarantined_retryable(tmp_path: Path) -> None:
    class DeniedClient:
        def submit_round(self, _payload: Mapping[str, Any]) -> dict[str, Any]:
            raise LedgerMindPermanentError("server returned 413", status=413, reason="http_413")

    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("first", {"idempotency_key": "first"})
    worker = DeliveryWorker(spool, cast(RoundSubmitter, DeniedClient()))

    assert worker.run_once() is True
    assert spool.stats().ready_delivery == 0
    assert spool.stats().inflight == 0
    assert spool.stats().failed == 1
    failed = json.loads(next(spool.failed_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert failed["delivery"]["failure_reason"] == "http_413"
    assert failed["delivery"]["retryable"] is True
    assert failed["delivery"]["attempts"] == 1


def test_conflict_is_permanent_with_source_round_reason(tmp_path: Path) -> None:
    class ConflictClient:
        def submit_round(self, _payload: Mapping[str, Any]) -> dict[str, Any]:
            raise LedgerMindConflictError()

    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("first", {"idempotency_key": "first"})
    DeliveryWorker(spool, cast(RoundSubmitter, ConflictClient())).run_once()

    assert spool.stats().failed == 1
    failed = json.loads(next(spool.failed_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert failed["delivery"]["failure_reason"] == "source_round_conflict"
    assert failed["delivery"]["retryable"] is True


def test_invalid_request_envelope_is_quarantined_retryable(tmp_path: Path) -> None:
    # A malformed envelope (no "request" mapping) is quarantined retryable rather
    # than retried forever. enqueue_ready always wraps a valid request, so build
    # the malformed envelope directly through the worker entry point.
    spool = FileSpool(tmp_path / "spool")
    worker = DeliveryWorker(spool, FakeClient())
    worker._process("first.json", {"delivery": {"attempts": 0}})

    assert spool.stats().failed == 1
    failed = json.loads(next(spool.failed_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert failed["delivery"]["failure_reason"] == "invalid_request_envelope"
    assert failed["delivery"]["retryable"] is True


def test_core_503_then_202_delivers_without_quarantine(tmp_path: Path) -> None:
    """A server 503 must retry until it accepts (202); no ceiling, no failed/."""

    class FlakyCoreClient:
        def __init__(self) -> None:
            self.calls = 0

        def submit_round(self, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            if self.calls < 3:
                raise LedgerMindNetworkError("server returned 503")
            return {"status": "accepted", "round_id": "round-1"}

    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("first", {"idempotency_key": "first"})
    client = FlakyCoreClient()
    worker = DeliveryWorker(spool, client)

    for _ in range(3):
        queued = spool.ready_dir / "first.json"
        data = json.loads(queued.read_text(encoding="utf-8"))
        data["delivery"]["next_attempt_at"] = 0
        spool.retry("first.json", data)
        worker.run_once()

    assert spool.stats().ready_delivery == 0
    assert spool.stats().inflight == 0
    assert spool.stats().failed == 0
    assert client.calls == 3


def test_unconfirmed_then_accepted_is_transient_without_quarantine(tmp_path: Path) -> None:
    """An unconfirmed ack is server-side/transient: keep retrying until confirmed."""

    class UnconfirmedOnceClient:
        def __init__(self) -> None:
            self.calls = 0

        def submit_round(self, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {}
            return {"status": "accepted", "round_id": "round-1"}

    spool = FileSpool(tmp_path / "spool")
    spool.enqueue_ready("first", {"idempotency_key": "first"})
    client = UnconfirmedOnceClient()
    worker = DeliveryWorker(spool, client)

    worker.run_once()  # unconfirmed -> stays queued
    assert spool.stats().ready_delivery == 1
    assert spool.stats().failed == 0
    queued = spool.ready_dir / "first.json"
    data = json.loads(queued.read_text(encoding="utf-8"))
    data["delivery"]["next_attempt_at"] = 0
    spool.retry("first.json", data)
    worker.run_once()  # accepted -> completed

    assert spool.stats().ready_delivery == 0
    assert spool.stats().failed == 0
    assert client.calls == 2


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
