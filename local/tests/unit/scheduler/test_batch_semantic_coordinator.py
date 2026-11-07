from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ledgermind_inference.batch_result_store import BatchResultNotReady
from ledgermind_inference.core_task_executor import (
    CoreTaskExecutor,
    GenericExecutionTask,
)
from ledgermind_inference.providers.batch_policy import BatchLimits
from ledgermind_inference.providers.openrouter_batch import BatchApiError
from ledgermind_inference.round_semantic_chunks import RoundSemanticChunkPlanner
from ledgermind_local.scheduler.batch_semantic_coordinator import (
    BatchSemanticCoordinator,
)
from ledgermind_local.scheduler.batch_semantic_store import BatchSemanticStore


def _task(
    task_id: str = "t1", *, operation: str = "operational_round_memory_preparation"
):
    operation_input: dict[str, Any] = {"raw_round_id": "round-1"}
    if "round_memory" in operation:
        operation_input["round_memory"] = {
            "version": "memory_write",
            "stage": "preparation",
        }
    return GenericExecutionTask(
        task_id=task_id,
        task_kind="generate_json",
        operation=operation,
        profile_slot="operational",
        operation_input=operation_input,
        model_request={
            "messages": [{"role": "user", "content": "extract"}],
            "mode": "strict_json_schema",
            "max_output_tokens": 8192,
            "output_contract": {
                "contract_name": "operational_round_memory_preparation",
                "json_schema": {"type": "object"},
                "schema_digest": "digest-1",
            },
        },
    )


class FakeBatchClient:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, list[dict[str, Any]]]] = []
        self.callback_urls: list[str | None] = []
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.parsed: dict[str, dict[str, dict[str, Any]]] = {}

    def format_request(
        self,
        custom_id: str,
        *,
        messages: list[dict[str, Any]],
        max_tokens: int = 8192,
        schema: dict[str, Any] | None = None,
        schema_name: str | None = None,
        reasoning_effort: str = "low",
    ) -> dict[str, Any]:
        return {
            "custom_id": custom_id,
            "body": {
                "messages": messages,
                "max_tokens": max_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema},
                },
            },
        }

    def submit_batch(
        self,
        requests: list[dict[str, Any]],
        *,
        model: str = "model",
        endpoint: str = "/v1/chat/completions",
        callback_url: str | None = None,
    ) -> str:
        batch_id = f"batch-{len(self.submitted) + 1}"
        self.callback_urls.append(callback_url)
        self.submitted.append((batch_id, list(requests)))
        return batch_id

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        return self.snapshots[batch_id]

    def parse_batch_results(
        self, batch_data: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        return self.parsed.get(str(batch_data.get("id")), {})


class SplitOnTooLargeClient(FakeBatchClient):
    def submit_batch(
        self,
        requests: list[dict[str, Any]],
        *,
        model: str = "model",
        endpoint: str = "/v1/chat/completions",
        callback_url: str | None = None,
    ) -> str:
        if len(requests) > 1:
            raise BatchApiError("too large", status_code=413, retryable=False)
        return super().submit_batch(
            requests,
            model=model,
            endpoint=endpoint,
            callback_url=callback_url,
        )


def _store(tmp_path: Path) -> BatchSemanticStore:
    return BatchSemanticStore(tmp_path / "batch.sqlite3")


def _coordinator(
    store: BatchSemanticStore,
    client: FakeBatchClient,
    *,
    max_wait_seconds: float = 0.0,
    callback_url: str | None = None,
    webhook_safety_interval_seconds: float = 900.0,
) -> BatchSemanticCoordinator:
    return BatchSemanticCoordinator(
        store=store,
        client=client,  # type: ignore[arg-type]
        worker_id="worker-1",
        limits=BatchLimits.openrouter(
            max_requests_per_batch=10,
            max_batch_bytes=10**9,
            soft_total_prompt_tokens=10**9,
        ),
        max_wait_seconds=max_wait_seconds,
        poll_interval_seconds=0.01,
        callback_url=callback_url,
        webhook_safety_interval_seconds=webhook_safety_interval_seconds,
    )


def test_is_batch_task_distinguishes_round_memory(tmp_path: Path) -> None:
    coordinator = _coordinator(_store(tmp_path), FakeBatchClient())

    assert coordinator.is_batch_task(_task())
    assert not coordinator.is_batch_task(_task(operation="agent_generation"))


def test_enqueue_is_idempotent_and_has_result_tracks_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = _coordinator(store, FakeBatchClient())
    task = _task()

    assert coordinator.enqueue(task, "space-1")
    assert not coordinator.enqueue(task, "space-1")
    assert not coordinator.has_result(task)

    store.mark_result(task.task_id, output={"ok": True})

    assert coordinator.has_result(task)


def test_failed_task_is_exposed_once_and_never_returned_as_delivery(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    coordinator = _coordinator(store, FakeBatchClient())
    task = _task()

    assert coordinator.enqueue(task, "space-1")
    store.mark_failed(task.task_id, "batch_result_missing")

    assert coordinator.tick() == []
    assert coordinator.has_result(task) is False
    assert coordinator.failure_code(task.task_id) == "batch_result_missing"
    assert coordinator.failure_pending(task.task_id)
    failures = coordinator.failures()
    assert [(failure.task_id, failure.error_code) for failure in failures] == [
        (task.task_id, "batch_result_missing")
    ]

    coordinator.mark_failure_delivered(task.task_id)

    assert not coordinator.failure_pending(task.task_id)
    assert coordinator.failures() == []


def test_tick_submits_after_max_wait_and_returns_completed_result(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(store, client)
    task = _task()

    coordinator.enqueue(task, "space-1")
    assert coordinator.tick() == []

    record = store.get(task.task_id)
    assert record is not None
    assert record.status == "submitted"
    assert record.batch_id is not None
    assert len(client.submitted) == 1

    client.snapshots[record.batch_id] = {
        "id": record.batch_id,
        "status": "completed",
        "results": [],
    }
    client.parsed[record.batch_id] = {
        record.custom_id: {
            "status": "completed",
            "output": {"status": "extracted"},
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }
    }

    deliveries = coordinator.tick()

    assert [delivery.task.task_id for delivery in deliveries] == [task.task_id]
    assert store.get(task.task_id).status == "result_ready"  # type: ignore[union-attr]
    assert store.jobs() == []

    coordinator.mark_delivered(task.task_id)

    assert store.get(task.task_id).status == "completed"  # type: ignore[union-attr]


def test_tick_submits_token_capacity_before_max_wait(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = BatchSemanticCoordinator(
        store=store,
        client=client,  # type: ignore[arg-type]
        worker_id="worker-1",
        limits=BatchLimits.openrouter(
            max_requests_per_batch=10,
            max_batch_bytes=10**9,
            soft_total_prompt_tokens=1,
        ),
        max_wait_seconds=9999,
        poll_interval_seconds=0.01,
    )
    first = _task("t1")
    second = _task("t2")
    coordinator.enqueue(first, "space-1")
    coordinator.enqueue(second, "space-1")

    assert coordinator.tick() == []

    assert client.submitted
    assert store.get(first.task_id).status == "submitted"  # type: ignore[union-attr]
    assert store.get(second.task_id).status == "submitted"  # type: ignore[union-attr]


def test_completed_with_transient_entry_requeues(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(store, client, max_wait_seconds=9999)
    task = _task()
    store.enqueue(
        task_id=task.task_id,
        memory_space_id="space-1",
        custom_id=task.task_id,
        payload=task.model_dump(mode="json"),
    )
    store.mark_submitted([task.task_id], "batch-1")
    store.create_job(batch_id="batch-1", expires_at="2030-01-01T00:00:00+00:00")
    client.snapshots["batch-1"] = {
        "id": "batch-1",
        "status": "completed",
        "results": [],
    }
    client.parsed["batch-1"] = {
        task.task_id: {
            "status": "failed",
            "status_code": 503,
            "error_code": "provider_http_error",
        }
    }

    assert coordinator.tick() == []

    record = store.get(task.task_id)
    assert record is not None
    assert record.status == "pending"
    assert record.attempts == 1
    assert store.jobs() == []


def test_completed_with_terminal_entry_fails(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(store, client, max_wait_seconds=9999)
    task = _task()
    store.enqueue(
        task_id=task.task_id,
        memory_space_id="space-1",
        custom_id=task.task_id,
        payload=task.model_dump(mode="json"),
    )
    store.mark_submitted([task.task_id], "batch-1")
    store.create_job(batch_id="batch-1", expires_at="2030-01-01T00:00:00+00:00")
    client.snapshots["batch-1"] = {
        "id": "batch-1",
        "status": "completed",
        "results": [],
    }
    client.parsed["batch-1"] = {
        task.task_id: {
            "status": "failed",
            "status_code": 400,
            "error_code": "provider_http_error",
        }
    }

    coordinator.tick()

    record = store.get(task.task_id)
    assert record is not None
    assert record.status == "failed"


def test_failed_batch_is_requeued(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(store, client, max_wait_seconds=9999)
    task = _task()
    store.enqueue(
        task_id=task.task_id,
        memory_space_id="space-1",
        custom_id=task.task_id,
        payload=task.model_dump(mode="json"),
    )
    store.mark_submitted([task.task_id], "batch-1")
    store.create_job(batch_id="batch-1", expires_at="2030-01-01T00:00:00+00:00")
    client.snapshots["batch-1"] = {"id": "batch-1", "status": "failed"}

    coordinator.tick()

    record = store.get(task.task_id)
    assert record is not None
    assert record.status == "pending"
    assert record.attempts == 1
    assert store.jobs() == []


def test_submit_413_splits_without_losing_tasks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = SplitOnTooLargeClient()
    coordinator = _coordinator(store, client)
    for task_id in ("t1", "t2"):
        coordinator.enqueue(_task(task_id), "space-1")

    coordinator.tick()

    assert len(client.submitted) == 2
    assert store.get("t1").status == "submitted"  # type: ignore[union-attr]
    assert store.get("t2").status == "submitted"  # type: ignore[union-attr]
    assert len(store.jobs()) == 2


def test_store_is_a_core_task_executor_batch_source(tmp_path: Path) -> None:
    store = _store(tmp_path)
    task = _task()
    executor = CoreTaskExecutor(
        json_provider=SimpleNamespace(),  # type: ignore[arg-type]
        embedding_provider=SimpleNamespace(),  # type: ignore[arg-type]
        profile_resolver=SimpleNamespace(),  # type: ignore[arg-type]
        generate_json_timeout_seconds=5.0,
        embed_texts_timeout_seconds=5.0,
        batch_result_source=store,
    )

    with pytest.raises(BatchResultNotReady):
        executor.execute(task)

    store.enqueue(
        task_id=task.task_id,
        memory_space_id="space-1",
        custom_id=task.task_id,
        payload=task.model_dump(mode="json"),
        contract_digest="digest-1",
    )
    store.mark_result(
        task.task_id,
        output={"status": "extracted"},
        usage={"prompt_tokens": 7, "completion_tokens": 3},
    )

    result = executor.execute(task)

    assert result.status == "completed"
    assert result.output == {"status": "extracted"}
    assert result.metadata["batch_cached_result"] is True


def test_empty_tick_is_stable(tmp_path: Path) -> None:
    coordinator = _coordinator(_store(tmp_path), FakeBatchClient())

    assert coordinator.tick() == []
    assert coordinator.tick() == []


def _chunkable_task(
    *,
    blocks: int = 3,
    task_id: str = "root-chunked",
) -> GenericExecutionTask:
    source_blocks = [
        {
            "block_id": f"b{index}",
            "channel": "user",
            "encoding": "text",
            "field": "text",
            "source_ref": "m1",
            "text": f"block-{index} " * 300,
        }
        for index in range(1, blocks + 1)
    ]
    packet = {
        "source_blocks": source_blocks,
        "conditions": {"user": [], "execution": []},
        "source_metadata": {"user": [{"user_ref": "m1"}], "execution": []},
        "evidence_completeness": {"complete": True},
        "semantic_language": "en",
    }
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "statements": {"type": "array", "items": {"type": "object"}},
        },
        "$defs": {
            "block_ref": {
                "type": "string",
                "enum": [block["block_id"] for block in source_blocks],
            },
            "user_condition_ref": {"type": "string", "enum": []},
        },
    }
    return GenericExecutionTask.model_validate(
        {
            "task_id": task_id,
            "task_kind": "generate_json",
            "operation": "operational_round_memory_preparation",
            "profile_slot": "operational",
            "operation_input": {
                "raw_round_id": "round-1",
                "round_memory": {"version": "memory_write", "stage": "preparation"},
            },
            "model_request": {
                "messages": [
                    {"role": "system", "content": "prepare memory"},
                    {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
                ],
                "max_output_tokens": 8192,
                "mode": "strict_json_schema",
                "output_contract": {
                    "contract_name": "operational_round_memory_preparation",
                    "schema_digest": "digest-preparation",
                    "json_schema": schema,
                },
            },
        }
    )


def _chunk_coordinator(
    store: BatchSemanticStore,
    client: FakeBatchClient,
) -> BatchSemanticCoordinator:
    return BatchSemanticCoordinator(
        store=store,
        client=client,  # type: ignore[arg-type]
        worker_id="worker-1",
        limits=BatchLimits.openrouter(
            max_requests_per_batch=10,
            max_batch_bytes=10**9,
            soft_total_prompt_tokens=10**9,
            target_prompt_tokens_per_request=1_200,
        ),
        chunk_planner=RoundSemanticChunkPlanner(max_prompt_tokens=1_200),
        min_chunk_prompt_tokens=1_000,
        max_wait_seconds=0.0,
        poll_interval_seconds=0.01,
    )


def _statement_for(custom_id: str) -> dict[str, Any]:
    suffix = custom_id.rsplit("_", 1)[-1]
    try:
        block = int(suffix) % 3 + 1
    except ValueError:
        block = 1
    return {
        "parts": [
            {"op": "rewrite", "blocks": [f"b{block}"], "text": f"statement-{block}"}
        ],
        "user_condition_refs": [],
        "execution_condition_refs": [],
        "facet": "event",
    }


def _complete_batch(
    client: FakeBatchClient,
    *,
    batch_id: str,
    custom_ids: list[str],
) -> None:
    client.snapshots[batch_id] = {"id": batch_id, "status": "completed"}
    client.parsed[batch_id] = {
        custom_id: {
            "status": "completed",
            "output": {
                "status": "extracted",
                "statements": [_statement_for(custom_id)],
            },
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }
        for custom_id in custom_ids
    }


def test_oversized_task_is_chunked_merged_and_delivered(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _chunk_coordinator(store, client)
    task = _chunkable_task()

    coordinator.enqueue(task, "space-1")
    assert coordinator.tick() == []

    root = store.get(task.task_id)
    assert root is not None
    assert root.status == "pending"
    chunks = store.chunks_for_root(task.task_id)
    assert len(chunks) > 1
    assert {chunk.status for chunk in chunks} == {"submitted"}
    assert len(client.submitted) == 1
    batch_id, requests = client.submitted[0]
    assert {request["custom_id"] for request in requests} == {
        chunk.custom_id for chunk in chunks
    }

    _complete_batch(
        client,
        batch_id=batch_id,
        custom_ids=[chunk.custom_id for chunk in chunks],
    )
    deliveries = coordinator.tick()

    assert [delivery.task.task_id for delivery in deliveries] == [task.task_id]
    root = store.get(task.task_id)
    assert root is not None
    assert root.status == "result_ready"
    assert root.result is not None
    assert root.result["status"] == "extracted"
    assert len(root.result["statements"]) == len(chunks)
    assert {
        statement["parts"][0]["blocks"][0] for statement in root.result["statements"]
    } <= {"b1", "b2", "b3"}
    assert root.usage == {
        "prompt_tokens": 10 * len(chunks),
        "completion_tokens": 2 * len(chunks),
    }
    assert store.chunks_for_root(task.task_id) == []
    assert store.jobs() == []

    coordinator.mark_delivered(task.task_id)
    assert store.get(task.task_id).status == "completed"  # type: ignore[union-attr]


def test_failed_chunk_resets_root_and_replans_smaller(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _chunk_coordinator(store, client)
    task = _chunkable_task()

    coordinator.enqueue(task, "space-1")
    coordinator.tick()
    first_chunks = store.chunks_for_root(task.task_id)
    batch_id, _ = client.submitted[0]
    client.snapshots[batch_id] = {"id": batch_id, "status": "completed"}
    client.parsed[batch_id] = {
        first_chunks[0].custom_id: {
            "status": "failed",
            "status_code": 400,
            "error_code": "provider_http_error",
        },
        **{
            chunk.custom_id: {
                "status": "completed",
                "output": {"status": "abstained_transient_only", "statements": []},
            }
            for chunk in first_chunks[1:]
        },
    }

    coordinator.tick()

    root = store.get(task.task_id)
    assert root is not None
    assert root.status == "pending"
    assert root.attempts == 1
    replanned = store.chunks_for_root(task.task_id)
    assert replanned
    assert {chunk.status for chunk in replanned} == {"submitted"}
    assert len(replanned) > len(first_chunks)
    assert len(client.submitted) == 2


def test_transient_chunk_failure_is_requeued_without_touching_root(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _chunk_coordinator(store, client)
    task = _chunkable_task()

    coordinator.enqueue(task, "space-1")
    coordinator.tick()
    chunks = store.chunks_for_root(task.task_id)
    batch_id, _ = client.submitted[0]
    client.snapshots[batch_id] = {"id": batch_id, "status": "completed"}
    client.parsed[batch_id] = {
        chunk.custom_id: {
            "status": "failed",
            "status_code": 503,
            "error_code": "provider_http_error",
        }
        for chunk in chunks
    }

    coordinator.tick()

    root = store.get(task.task_id)
    assert root is not None
    assert root.status == "pending"
    assert root.attempts == 0
    requeued = store.chunks_for_root(task.task_id)
    assert {chunk.attempts for chunk in requeued} == {1}
    # The same tick resubmits the requeued chunks in a fresh batch.
    assert len(client.submitted) == 2
    assert {chunk.status for chunk in requeued} == {"submitted"}


def test_missing_chunk_output_resets_root(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _chunk_coordinator(store, client)
    task = _chunkable_task()

    coordinator.enqueue(task, "space-1")
    coordinator.tick()
    chunks = store.chunks_for_root(task.task_id)
    batch_id, _ = client.submitted[0]
    client.snapshots[batch_id] = {"id": batch_id, "status": "completed"}
    client.parsed[batch_id] = {
        chunk.custom_id: {
            "status": "completed",
            "output": [],
            "usage": {},
        }
        for chunk in chunks
    }

    coordinator.tick()

    root = store.get(task.task_id)
    assert root is not None
    assert root.status == "pending"
    assert root.attempts == 1
    assert store.chunks_for_root(task.task_id)


def _submitted_job(
    store: BatchSemanticStore,
    coordinator: BatchSemanticCoordinator,
    client: FakeBatchClient,
    task: GenericExecutionTask,
) -> str:
    coordinator.enqueue(task, "space-1")
    coordinator.tick()
    record = store.get(task.task_id)
    assert record is not None and record.batch_id is not None
    return record.batch_id


def test_fresh_batch_404_is_not_treated_as_expired(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(store, client)
    task = _task()
    batch_id = _submitted_job(store, coordinator, client, task)

    def not_found(_: str) -> dict[str, Any]:
        raise BatchApiError("not found yet", status_code=404, expired=True)

    client.get_batch = not_found  # type: ignore[assignment]
    coordinator.tick()

    record = store.get(task.task_id)
    assert record is not None
    assert record.status == "submitted"
    assert [job.batch_id for job in store.jobs()] == [batch_id]
    assert store.jobs()[0].poll_errors == 0


def test_batch_404_after_grace_is_expired(tmp_path: Path) -> None:
    import sqlite3
    from datetime import datetime, timedelta, timezone

    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(store, client)
    task = _task()
    batch_id = _submitted_job(store, coordinator, client, task)

    old = (
        datetime.now(timezone.utc)
        - timedelta(minutes=30)
    ).isoformat()
    with sqlite3.connect(store.path) as db:
        db.execute(
            "UPDATE batch_jobs SET submitted_at = ?, next_poll_at = ? WHERE batch_id = ?",
            (old, old, batch_id),
        )

    def not_found(_: str) -> dict[str, Any]:
        raise BatchApiError("gone", status_code=404, expired=True)

    client.get_batch = not_found  # type: ignore[assignment]
    coordinator.tick()

    record = store.get(task.task_id)
    assert record is not None
    # The expired batch is abandoned; because max_wait is zero the same tick
    # is allowed to submit the task again in a fresh batch.
    assert record.attempts == 1
    assert record.batch_id != batch_id
    assert batch_id not in {job.batch_id for job in store.jobs()}


def test_batch_410_is_expired_immediately(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(store, client)
    task = _task()
    batch_id = _submitted_job(store, coordinator, client, task)

    def gone(_: str) -> dict[str, Any]:
        raise BatchApiError("gone", status_code=410, expired=True)

    client.get_batch = gone  # type: ignore[assignment]
    coordinator.tick()

    record = store.get(task.task_id)
    assert record is not None
    assert record.attempts == 1
    assert batch_id not in {job.batch_id for job in store.jobs()}


def test_object_resolution_is_a_batch_task(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(store, client)
    task = _task(task_id="or-1", operation="object_resolution")

    assert coordinator.is_batch_task(task)
    assert coordinator.enqueue(task, "space-1")
    coordinator.tick()

    record = store.get(task.task_id)
    assert record is not None and record.batch_id is not None
    client.snapshots[record.batch_id] = {
        "id": record.batch_id,
        "status": "completed",
        "results": [],
    }
    client.parsed[record.batch_id] = {
        record.custom_id: {
            "status": "completed",
            "output": {"components": []},
        }
    }

    deliveries = coordinator.tick()

    assert [delivery.task.task_id for delivery in deliveries] == ["or-1"]


def test_native_decision_is_not_a_batch_task(tmp_path: Path) -> None:
    store = _store(tmp_path)
    coordinator = _coordinator(store, FakeBatchClient())
    task = _task(task_id="or-decide", operation="object_resolution").model_copy(
        update={
            "task_kind": "decide",
            "decision_request": {"schema_version": 2, "state": {}, "questions": {}},
        }
    )

    assert not coordinator.is_batch_task(task)


def test_callback_url_is_sent_and_webhook_mode_waits_for_it(
    tmp_path: Path,
) -> None:
    from datetime import datetime, timezone

    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(
        store,
        client,
        callback_url="https://example.test/openrouter-batch",
    )

    coordinator.enqueue(_task(), "space-1")
    coordinator.tick()

    assert client.callback_urls == ["https://example.test/openrouter-batch"]
    job = store.jobs()[0]
    delta = (
        datetime.fromisoformat(job.next_poll_at) - datetime.now(timezone.utc)
    ).total_seconds()
    assert 600 < delta <= 900


def test_webhook_wake_makes_a_batch_due_immediately(tmp_path: Path) -> None:
    store = _store(tmp_path)
    client = FakeBatchClient()
    coordinator = _coordinator(
        store,
        client,
        callback_url="https://example.test/openrouter-batch",
    )
    task = _task()
    coordinator.enqueue(task, "space-1")
    coordinator.tick()

    record = store.get(task.task_id)
    assert record is not None and record.batch_id is not None
    client.snapshots[record.batch_id] = {
        "id": record.batch_id,
        "status": "completed",
        "results": [],
    }
    client.parsed[record.batch_id] = {
        record.custom_id: {
            "status": "completed",
            "output": {"status": "extracted"},
        }
    }

    # The safety poll is still in the future.
    assert coordinator.tick() == []
    assert store.wake_batch(record.batch_id, delay_seconds=0)
    deliveries = coordinator.tick()

    assert [delivery.task.task_id for delivery in deliveries] == [task.task_id]
    assert store.jobs() == []
