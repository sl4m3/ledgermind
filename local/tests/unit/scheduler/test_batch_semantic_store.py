from __future__ import annotations

from pathlib import Path

from ledgermind_local.scheduler.batch_semantic_store import BatchSemanticStore


def _store(tmp_path: Path) -> BatchSemanticStore:
    return BatchSemanticStore(tmp_path / "batch.sqlite3")


def test_enqueue_is_idempotent_and_orders_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert store.enqueue(
        task_id="t2",
        memory_space_id="space",
        custom_id="c2",
        payload={"task_id": "t2"},
    )
    assert store.enqueue(
        task_id="t1",
        memory_space_id="space",
        custom_id="c1",
        payload={"task_id": "t1"},
    )
    assert not store.enqueue(
        task_id="t1",
        memory_space_id="space",
        custom_id="c1",
        payload={"task_id": "t1"},
    )

    pending = store.pending()
    assert {record.task_id for record in pending} == {"t1", "t2"}
    assert all(record.status == "pending" for record in pending)


def test_mark_submitted_removes_task_from_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        task_id="t1",
        memory_space_id="space",
        custom_id="c1",
        payload={"task_id": "t1"},
    )

    store.mark_submitted(["t1"], "batch-1")

    assert store.pending() == []
    record = store.get("t1")
    assert record is not None
    assert record.status == "submitted"
    assert record.batch_id == "batch-1"


def test_record_submission_registers_task_and_job_together(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        task_id="t1",
        memory_space_id="space",
        custom_id="c1",
        payload={"task_id": "t1"},
    )

    store.record_submission(
        ["t1"],
        "batch-1",
        expires_at="2030-01-01T00:00:00+00:00",
    )

    record = store.get("t1")
    assert record is not None
    assert record.status == "submitted"
    assert record.batch_id == "batch-1"
    assert [job.batch_id for job in store.jobs()] == ["batch-1"]
    assert store.pending() == []


def test_result_lookup_and_delivery_are_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        task_id="t1",
        memory_space_id="space",
        custom_id="c1",
        payload={"task_id": "t1"},
        contract_digest="digest-1",
    )
    store.mark_submitted(["t1"], "batch-1")
    store.mark_result(
        "t1",
        output={"status": "extracted", "statements": []},
        usage={"prompt_tokens": 10, "completion_tokens": 2},
    )

    entry = store.lookup(task_id="t1", keys=[])
    assert entry == {
        "status": "completed",
        "output": {"status": "extracted", "statements": []},
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        "batch_id": "batch-1",
        "contract_digest": "digest-1",
    }

    store.mark_delivered("t1")
    record = store.get("t1")
    assert record is not None
    assert record.status == "completed"
    assert store.lookup(task_id="t1", keys=[]) == entry


def test_lookup_by_custom_id_and_legacy_key(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        task_id="task-uuid",
        memory_space_id="space",
        custom_id="I1-S1-0001__preparation",
        payload={"task_id": "task-uuid"},
    )
    store.mark_result("task-uuid", output={"ok": True})

    assert store.lookup(task_id="missing", keys=["I1-S1-0001__preparation"]) is not None
    assert store.lookup(task_id="missing", keys=["unknown"]) is None


def test_failed_lookup_is_not_a_completed_result(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        task_id="t1",
        memory_space_id="space",
        custom_id="c1",
        payload={"task_id": "t1"},
    )
    store.mark_failed("t1", "invalid_request")

    entry = store.lookup(task_id="t1", keys=[])
    assert entry == {"status": "failed", "error_code": "invalid_request"}
    assert store.get("t1").status == "failed"  # type: ignore[union-attr]


def test_failed_task_can_be_reenqueued(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.enqueue(
        task_id="t1",
        memory_space_id="space",
        custom_id="c1",
        payload={"task_id": "t1"},
    )
    store.mark_failed("t1", "transient_provider_error")

    assert store.enqueue(
        task_id="t1",
        memory_space_id="space",
        custom_id="c1",
        payload={"task_id": "t1-retry"},
    )
    record = store.get("t1")
    assert record is not None
    assert record.status == "pending"
    assert record.result is None
    assert record.payload == {"task_id": "t1-retry"}
    assert store.lookup(task_id="t1", keys=[]) == {
        "status": "failed",
        "error_code": "batch_result_unavailable",
    }


def test_requeue_batch_returns_tasks_to_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for task_id in ("t1", "t2"):
        store.enqueue(
            task_id=task_id,
            memory_space_id="space",
            custom_id=f"c-{task_id}",
            payload={"task_id": task_id},
        )
    store.mark_submitted(["t1", "t2"], "batch-1")

    requeued = store.requeue_batch("batch-1", "batch_expired")

    assert set(requeued) == {"t1", "t2"}
    assert {record.task_id for record in store.pending()} == {"t1", "t2"}
    assert store.get("t1").attempts == 1  # type: ignore[union-attr]
    assert store.get("t1").batch_id is None  # type: ignore[union-attr]


def test_job_lifecycle(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_job(batch_id="batch-1", expires_at="2030-01-01T00:00:00+00:00")
    store.create_job(batch_id="batch-1", expires_at="2030-01-01T00:00:00+00:00")

    jobs = store.jobs()
    assert [job.batch_id for job in jobs] == ["batch-1"]
    assert jobs[0].status == "submitted"

    store.update_job(
        "batch-1",
        status="in_progress",
        next_poll_at="2030-01-01T00:00:10+00:00",
        poll_errors=2,
    )
    job = store.jobs()[0]
    assert job.status == "in_progress"
    assert job.poll_errors == 2

    store.delete_job("batch-1")
    assert store.jobs() == []


def _root(store: BatchSemanticStore, task_id: str = "root-1") -> None:
    store.enqueue(
        task_id=task_id,
        memory_space_id="space",
        custom_id=f"custom-{task_id}",
        payload={"task_id": task_id},
    )


def _chunks(count: int = 2) -> list[dict[str, object]]:
    return [
        {
            "chunk_id": f"root-1::chunk::{index:04d}",
            "custom_id": f"root-1__chunk_{index:04d}",
            "payload": {"task_id": f"root-1::chunk::{index:04d}"},
        }
        for index in range(count)
    ]


def test_plan_chunks_hides_root_from_pending_and_orders_chunks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _root(store)

    assert store.plan_chunks("root-1", _chunks(2))
    assert not store.plan_chunks("root-1", _chunks(2))
    assert store.pending() == []
    assert [chunk.chunk_index for chunk in store.pending_chunks()] == [0, 1]
    assert all(chunk.chunk_total == 2 for chunk in store.chunks_for_root("root-1"))


def test_plan_chunks_requires_a_pending_root(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert not store.plan_chunks("missing", _chunks())
    _root(store)
    store.mark_submitted(["root-1"], "batch-0")

    assert not store.plan_chunks("root-1", _chunks())


def test_record_batch_submission_marks_root_and_chunks_atomically(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _root(store)
    store.plan_chunks("root-1", _chunks(2))
    chunk_ids = [chunk.chunk_id for chunk in store.chunks_for_root("root-1")]

    store.record_batch_submission(
        ["root-1"],
        chunk_ids,
        "batch-1",
        expires_at="2030-01-01T00:00:00+00:00",
    )

    assert store.get("root-1").status == "submitted"  # type: ignore[union-attr]
    assert {
        chunk.status for chunk in store.chunks_for_batch("batch-1")
    } == {"submitted"}
    assert [job.batch_id for job in store.jobs()] == ["batch-1"]
    assert store.pending_chunks() == []


def test_complete_chunked_root_publishes_result_and_removes_chunks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _root(store)
    store.plan_chunks("root-1", _chunks(2))
    store.complete_chunked_root(
        "root-1",
        output={"status": "extracted", "statements": []},
        usage={"prompt_tokens": 10, "completion_tokens": 2},
    )

    record = store.get("root-1")
    assert record is not None
    assert record.status == "result_ready"
    assert record.result == {"status": "extracted", "statements": []}
    assert store.chunks_for_root("root-1") == []
    assert store.lookup(task_id="root-1", keys=[])["status"] == "completed"


def test_reset_chunked_root_returns_root_to_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _root(store)
    store.plan_chunks("root-1", _chunks(2))

    attempts = store.reset_chunked_root("root-1", "chunk_failed")

    assert attempts == 1
    assert store.chunks_for_root("root-1") == []
    assert [record.task_id for record in store.pending()] == ["root-1"]


def test_requeue_chunks_batch_returns_chunks_to_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _root(store)
    store.plan_chunks("root-1", _chunks(2))
    chunk_ids = [chunk.chunk_id for chunk in store.chunks_for_root("root-1")]
    store.record_batch_submission(
        [],
        chunk_ids,
        "batch-1",
        expires_at="2030-01-01T00:00:00+00:00",
    )

    requeued = store.requeue_chunks_batch("batch-1", "batch_expired")

    assert set(requeued) == set(chunk_ids)
    chunks = store.chunks_for_root("root-1")
    assert {chunk.status for chunk in chunks} == {"pending"}
    assert {chunk.attempts for chunk in chunks} == {1}
    assert {chunk.batch_id for chunk in chunks} == {None}


def test_record_batch_submission_keeps_explicit_next_poll_at(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _root(store)
    store.plan_chunks("root-1", _chunks(1))
    chunk_ids = [chunk.chunk_id for chunk in store.chunks_for_root("root-1")]

    store.record_batch_submission(
        [],
        chunk_ids,
        "batch-1",
        expires_at="2030-01-01T00:00:00+00:00",
        next_poll_at="2030-01-01T00:05:00+00:00",
    )

    job = store.jobs()[0]
    assert job.next_poll_at == "2030-01-01T00:05:00+00:00"
