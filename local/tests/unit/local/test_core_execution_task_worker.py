from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from ledgermind_local.core_gateway.contracts import DomainRejectedError
from ledgermind_local.scheduler import core_execution_task_worker as worker_module
from ledgermind_local.scheduler.batch_semantic_coordinator import (
    BatchDelivery,
    BatchFailure,
)
from ledgermind_local.scheduler.core_execution_task_worker import (
    CoreExecutionTaskWorker,
    _batch_failure_code,
    _execution_result_is_retryable,
    classify_execution_error,
)


def test_process_once_closes_discovery_connection_before_provider_work(
    monkeypatch,
) -> None:
    events: list[str] = []

    class Connection:
        closed = False

        def commit(self) -> None:
            events.append("commit")

        def execute(self, _query: str):
            assert not self.closed
            return SimpleNamespace(fetchall=lambda: [("space-1",)])

        def close(self) -> None:
            self.closed = True
            events.append("close")

    connection = Connection()

    class Gateway:
        def require_capabilities(self, _capability: str) -> None:
            return None

        def poll_execution_tasks(self, _command):
            assert connection.closed
            events.append("poll")
            return SimpleNamespace(tasks=[])

    monkeypatch.setattr(
        worker_module.migrations,
        "apply_migrations",
        lambda _connection: events.append("migrate"),
    )
    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=Gateway(),
        executor=SimpleNamespace(),
        worker_id="test-worker",
        connection_factory=lambda _path: connection,
    )

    assert worker.process_once() == 0
    assert events == ["migrate", "commit", "close", "poll"]


def test_auth_failure_stops_polling_other_spaces_and_future_cycles(monkeypatch) -> None:
    polls: list[str] = []

    class Connection:
        def commit(self) -> None:
            pass

        def execute(self, _query: str):
            return SimpleNamespace(fetchall=lambda: [("space-1",), ("space-2",)])

        def close(self) -> None:
            pass

    class Gateway:
        def require_capabilities(self, _capability: str) -> None:
            pass

        def poll_execution_tasks(self, command):
            polls.append(command.memory_space_id)
            return SimpleNamespace(tasks=[{"task_id": "task-1"}])

    monkeypatch.setattr(
        worker_module.migrations, "apply_migrations", lambda _connection: None
    )
    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=Gateway(),
        executor=SimpleNamespace(),  # type: ignore[arg-type]
        worker_id="test-worker",
        connection_factory=lambda _path: Connection(),
    )

    def process_tasks(_tasks: object, _space: str) -> None:
        worker._open_provider_circuit_on_failure(
            SimpleNamespace(status="failed", error_code="authentication_failed")
        )

    monkeypatch.setattr(worker, "_process_tasks", process_tasks)
    assert worker.process_once() == 1
    assert worker.provider_circuit_open
    assert worker.process_once() == 0
    assert polls == ["space-1"]


def test_non_auth_provider_failure_does_not_open_circuit() -> None:
    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=SimpleNamespace(),  # type: ignore[arg-type]
        executor=SimpleNamespace(),  # type: ignore[arg-type]
        worker_id="test-worker",
    )
    worker._open_provider_circuit_on_failure(
        SimpleNamespace(status="failed", error_code="provider_unavailable")
    )
    assert not worker.provider_circuit_open


def test_transient_provider_result_is_retryable() -> None:
    result = SimpleNamespace(status="failed", error_code="transient_provider_error")

    assert _execution_result_is_retryable(result) is True


def test_embedding_provider_unavailable_result_is_retryable() -> None:
    result = SimpleNamespace(status="failed", error_code="provider_unavailable")

    assert _execution_result_is_retryable(result) is True


def test_embedding_transport_result_is_retryable() -> None:
    result = SimpleNamespace(status="failed", error_code="provider_transport_error")

    assert _execution_result_is_retryable(result) is True


def test_schema_failure_result_is_not_retryable() -> None:
    result = SimpleNamespace(status="failed", error_code="schema_shape_failure")

    assert _execution_result_is_retryable(result) is False


def test_core_rejection_preserves_public_domain_reason() -> None:
    classification = classify_execution_error(
        DomainRejectedError("UNKNOWN_OBJECT_CANDIDATE", "candidate m7 was not offered")
    )

    assert classification.error_code == "core_rejected_unknown_object_candidate"
    assert classification.retryable is False


def test_invalid_request_records_safe_round_semantic_reason() -> None:
    classification = classify_execution_error(
        DomainRejectedError(
            "INVALID_REQUEST",
            "round_semantic_user_provenance_invalid: claim c4 contains an unknown ref",
        )
    )

    assert (
        classification.error_code
        == "core_rejected_round_semantic_user_provenance_invalid"
    )
    assert "c4" not in classification.error_code


def test_invalid_request_distinguishes_round_semantic_validation_failures() -> None:
    grounding = classify_execution_error(
        DomainRejectedError(
            "INVALID_REQUEST",
            "invalid stored record: object_missing_grounding_refs: object o2 is ungrounded",
        )
    )
    unknown_object = classify_execution_error(
        DomainRejectedError(
            "INVALID_REQUEST",
            "invalid stored record: round claim references unknown object o9",
        )
    )

    assert (
        grounding.error_code == "core_rejected_round_semantic_object_grounding_missing"
    )
    assert (
        unknown_object.error_code == "core_rejected_round_semantic_claim_object_unknown"
    )
    assert "o2" not in grounding.error_code
    assert "o9" not in unknown_object.error_code


def test_semantic_incomplete_rejection_keeps_a_precise_content_free_reason() -> None:
    classification = classify_execution_error(
        DomainRejectedError(
            "INVALID_REQUEST",
            "round_semantic_semantic_incomplete: private evidence details",
        )
    )

    assert (
        classification.error_code == "core_rejected_round_semantic_semantic_incomplete"
    )
    assert classification.retryable is False


def test_unknown_invalid_request_does_not_persist_remote_detail() -> None:
    classification = classify_execution_error(
        DomainRejectedError("INVALID_REQUEST", "unexpected private payload value")
    )

    assert classification.error_code == "core_rejected_invalid_request"


def test_schema_failure_gets_one_retry_on_configured_provider_fallback(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []
    retry_result = SimpleNamespace(status="completed")

    class Gateway:
        def require_capabilities(self, _capability: str) -> None:
            return None

    class Executor:
        def execute(self, _task: object, **kwargs: object) -> object:
            calls.append(kwargs)
            return retry_result

    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=Gateway(),
        executor=Executor(),  # type: ignore[arg-type]
        worker_id="test-worker",
    )
    delivered: list[object] = []
    monkeypatch.setattr(
        worker,
        "_deliver_result",
        lambda _task, result, _memory_space_id: delivered.append(result),
    )

    worker._deliver_result_with_structured_retry(
        SimpleNamespace(task_kind="generate_json", task_id="task-1"),
        SimpleNamespace(status="failed", error_code="schema_shape_failure"),
        "space",
    )

    assert calls == [{"force_provider_fallback": True, "skip_batch_cache": True}]
    assert delivered == [retry_result]


def test_memory_write_schema_failure_retries_the_same_provider_route(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []
    retry_result = SimpleNamespace(status="completed")

    class Gateway:
        def require_capabilities(self, _capability: str) -> None:
            return None

    class Executor:
        def execute(self, _task: object, **kwargs: object) -> object:
            calls.append(kwargs)
            return retry_result

    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=Gateway(),
        executor=Executor(),  # type: ignore[arg-type]
        worker_id="test-worker",
    )
    delivered: list[object] = []
    monkeypatch.setattr(
        worker,
        "_deliver_result",
        lambda _task, result, _memory_space_id: delivered.append(result),
    )

    worker._deliver_result_with_structured_retry(
        SimpleNamespace(
            task_kind="generate_json",
            task_id="task-1",
            operation_input={"resolution_pipeline": "memory_write"},
        ),
        SimpleNamespace(status="failed", error_code="schema_shape_failure"),
        "space",
    )

    assert calls == [{"force_provider_fallback": False, "skip_batch_cache": True}]
    assert delivered == [retry_result]


def test_core_structural_rejection_gets_one_retry_on_configured_provider_fallback(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []
    retry_result = SimpleNamespace(status="completed")

    class Gateway:
        def require_capabilities(self, _capability: str) -> None:
            return None

    class Executor:
        def execute(self, _task: object, **kwargs: object) -> object:
            calls.append(kwargs)
            return retry_result

    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=Gateway(),
        executor=Executor(),  # type: ignore[arg-type]
        worker_id="test-worker",
    )
    deliveries = 0

    def deliver(_task: object, _result: object, _memory_space_id: str) -> None:
        nonlocal deliveries
        deliveries += 1
        if deliveries == 1:
            raise DomainRejectedError("INVALID_REQUEST", "strict output mismatch")

    monkeypatch.setattr(worker, "_deliver_result", deliver)

    worker._deliver_result_with_structured_retry(
        SimpleNamespace(task_kind="generate_json", task_id="task-1"),
        SimpleNamespace(status="completed", error_code=None),
        "space",
    )

    assert calls == [{"force_provider_fallback": True, "skip_batch_cache": True}]
    assert deliveries == 2


def test_collect_batch_deliveries_delivers_and_marks(monkeypatch) -> None:
    delivered: list[tuple[str, str, str]] = []
    marked: list[str] = []

    class Coordinator:
        def failures(self) -> list[object]:
            return []

        def tick(self) -> list[BatchDelivery]:
            return [
                BatchDelivery(
                    task=SimpleNamespace(task_id="task-1"),
                    memory_space_id="space",
                )
            ]

        def mark_delivered(self, task_id: str) -> None:
            marked.append(task_id)

        def mark_failed(self, _task_id: str, _error_code: str) -> None:
            raise AssertionError("completed delivery must not be marked failed")

        def mark_failure_delivered(self, _task_id: str) -> None:
            raise AssertionError("completed delivery has no failure")

    class Executor:
        def execute(self, _task: object) -> object:
            return SimpleNamespace(status="completed")

    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=SimpleNamespace(),  # type: ignore[arg-type]
        executor=Executor(),  # type: ignore[arg-type]
        worker_id="test-worker",
        batch_coordinator=Coordinator(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        worker,
        "_deliver_result_with_structured_retry",
        lambda task, result, space, **_kwargs: delivered.append(
            (task.task_id, result.status, space)
        ),
    )

    worker._collect_batch_deliveries()

    assert delivered == [("task-1", "completed", "space")]
    assert marked == ["task-1"]


def test_batch_domain_rejection_fails_once_without_provider_retry(
    monkeypatch,
) -> None:
    executor_calls: list[str] = []
    failures: list[tuple[str, str, bool]] = []
    marked_failed: list[tuple[str, str]] = []
    marked_delivered: list[str] = []

    class Gateway:
        def submit_execution_result(self, _command: object) -> object:
            raise DomainRejectedError(
                "UNKNOWN_OBJECT_CANDIDATE", "candidate m7 was not offered"
            )

        def fail_execution_task(self, command: object) -> None:
            failures.append((command.task_id, command.error_code, command.retryable))

    class Executor:
        def execute(self, task: object) -> object:
            executor_calls.append(task.task_id)
            return SimpleNamespace(status="completed", error_code=None)

    class Coordinator:
        def failures(self) -> list[object]:
            return []

        def tick(self) -> list[BatchDelivery]:
            return [
                BatchDelivery(
                    task=SimpleNamespace(task_id="task-1"),
                    memory_space_id="space",
                )
            ]

        def mark_delivered(self, task_id: str) -> None:
            marked_delivered.append(task_id)

        def mark_failed(self, task_id: str, error_code: str) -> None:
            marked_failed.append((task_id, error_code))

        def mark_failure_delivered(self, _task_id: str) -> None:
            return None

    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=Gateway(),  # type: ignore[arg-type]
        executor=Executor(),  # type: ignore[arg-type]
        worker_id="test-worker",
        batch_coordinator=Coordinator(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(worker, "_record_egress_audit", lambda *_args: None)
    monkeypatch.setattr(
        worker,
        "_deliver_result",
        lambda *_args: (_ for _ in ()).throw(
            DomainRejectedError(
                "UNKNOWN_OBJECT_CANDIDATE", "candidate m7 was not offered"
            )
        ),
    )

    worker._collect_batch_deliveries()

    assert executor_calls == ["task-1"]
    assert failures == [("task-1", "core_rejected_unknown_object_candidate", False)]
    assert marked_failed == [("task-1", "core_rejected_unknown_object_candidate")]
    assert marked_delivered == []


def test_batch_transient_core_error_keeps_result_ready(monkeypatch) -> None:
    marked_failed: list[tuple[str, str]] = []
    marked_delivered: list[str] = []

    class Gateway:
        pass

    class Executor:
        def execute(self, _task: object) -> object:
            return SimpleNamespace(status="completed", error_code=None)

    class Coordinator:
        def failures(self) -> list[object]:
            return []

        def tick(self) -> list[BatchDelivery]:
            return [
                BatchDelivery(
                    task=SimpleNamespace(task_id="task-1"),
                    memory_space_id="space",
                )
            ]

        def mark_delivered(self, task_id: str) -> None:
            marked_delivered.append(task_id)

        def mark_failed(self, task_id: str, error_code: str) -> None:
            marked_failed.append((task_id, error_code))

        def mark_failure_delivered(self, _task_id: str) -> None:
            return None

    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=Gateway(),  # type: ignore[arg-type]
        executor=Executor(),  # type: ignore[arg-type]
        worker_id="test-worker",
        batch_coordinator=Coordinator(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(worker, "_record_egress_audit", lambda *_args: None)
    monkeypatch.setattr(
        worker,
        "_deliver_result",
        lambda *_args: (_ for _ in ()).throw(
            worker_module.TransientCoreError("core unavailable")
        ),
    )

    worker._collect_batch_deliveries()

    assert marked_failed == []
    assert marked_delivered == []


def test_batch_failure_is_delivered_once_and_marked() -> None:
    failures: list[tuple[str, str, bool]] = []
    marked_delivered: list[str] = []

    class Gateway:
        def fail_execution_task(self, command: object) -> None:
            failures.append((command.task_id, command.error_code, command.retryable))

    class Coordinator:
        def __init__(self) -> None:
            self.pending = True

        def failures(self) -> list[BatchFailure]:
            if not self.pending:
                return []
            return [
                BatchFailure(
                    task_id="task-1",
                    memory_space_id="space",
                    error_code="batch_result_missing",
                )
            ]

        def mark_failure_delivered(self, task_id: str) -> None:
            marked_delivered.append(task_id)
            self.pending = False

        def tick(self) -> list[BatchDelivery]:
            return []

    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=Gateway(),  # type: ignore[arg-type]
        executor=SimpleNamespace(),  # type: ignore[arg-type]
        worker_id="test-worker",
        batch_coordinator=Coordinator(),  # type: ignore[arg-type]
    )

    worker._collect_batch_deliveries()
    worker._collect_batch_deliveries()

    assert failures == [("task-1", "batch_result_missing", False)]
    assert marked_delivered == ["task-1"]


def test_process_tasks_reports_a_failed_batch_without_reenqueueing(monkeypatch) -> None:
    failures: list[tuple[str, str, bool]] = []
    marked: list[str] = []
    enqueued: list[str] = []
    executed: list[object] = []
    task = SimpleNamespace(
        task_id="task-1",
        operation="operational_round_memory_preparation",
        operation_input={"round_memory": {"stage": "preparation"}},
    )

    class Gateway:
        def fail_execution_task(self, command: object) -> None:
            failures.append((command.task_id, command.error_code, command.retryable))

    class Coordinator:
        def __init__(self) -> None:
            self.pending = True

        def is_batch_task(self, _task: object) -> bool:
            return True

        def has_result(self, _task: object) -> bool:
            return False

        def failure_pending(self, _task_id: str) -> bool:
            return self.pending

        def failure_code(self, _task_id: str) -> str:
            return "batch_result_missing"

        def mark_failure_delivered(self, task_id: str) -> None:
            marked.append(task_id)
            self.pending = False

        def enqueue(self, candidate: object, memory_space_id: str) -> bool:
            enqueued.append(candidate.task_id)
            # The durable store refuses to revive a failed task.
            return False

    class Executor:
        def execute_batch(self, tasks: object) -> object:
            executed.append(tasks)
            return []

    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=Gateway(),  # type: ignore[arg-type]
        executor=Executor(),  # type: ignore[arg-type]
        worker_id="test-worker",
        batch_coordinator=Coordinator(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        worker_module,
        "execution_task_from_wire",
        lambda _raw_task, _memory_space_id: task,
    )

    worker._process_tasks([{"task_id": "task-1"}], "space")
    worker._process_tasks([{"task_id": "task-1"}], "space")

    assert failures == [
        ("task-1", "batch_result_missing", False),
        ("task-1", "batch_result_missing", False),
    ]
    assert marked == ["task-1"]
    assert enqueued == []
    assert executed == []


def test_process_tasks_defers_round_memory_to_batch_coordinator(monkeypatch) -> None:
    enqueued: list[tuple[str, str]] = []
    task = SimpleNamespace(
        task_id="task-1",
        operation="operational_round_memory_preparation",
        operation_input={"round_memory": {"stage": "preparation"}},
    )

    class Coordinator:
        def is_batch_task(self, _task: object) -> bool:
            return True

        def has_result(self, _task: object) -> bool:
            return False

        def failure_pending(self, _task_id: str) -> bool:
            return False

        def failure_code(self, _task_id: str) -> None:
            return None

        def enqueue(self, candidate: object, memory_space_id: str) -> bool:
            enqueued.append((candidate.task_id, memory_space_id))
            return True

    class Executor:
        def execute_batch(self, _tasks: object) -> object:
            raise AssertionError("deferred batch tasks must not execute immediately")

    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=SimpleNamespace(),  # type: ignore[arg-type]
        executor=Executor(),  # type: ignore[arg-type]
        worker_id="test-worker",
        batch_coordinator=Coordinator(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        worker_module,
        "execution_task_from_wire",
        lambda _raw_task, _memory_space_id: task,
    )

    worker._process_tasks([{"task_id": "task-1"}], "space")

    assert enqueued == [("task-1", "space")]


def test_worker_persists_content_free_audit_for_each_executor_result(tmp_path) -> None:
    database = tmp_path / "rounds.db"
    connection = sqlite3.connect(database)
    worker_module.migrations.apply_migrations(connection)
    connection.execute(
        "INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) "
        "VALUES ('space', 'test', '2026-09-03T00:00:00Z', '2026-09-03T00:00:00Z')"
    )
    connection.commit()
    connection.close()

    class Gateway:
        def require_capabilities(self, _capability: str) -> None:
            return None

    worker = CoreExecutionTaskWorker(
        database_path=database,
        gateway=Gateway(),
        executor=SimpleNamespace(),  # type: ignore[arg-type]
        worker_id="test-worker",
    )
    task = SimpleNamespace(
        task_id="task-1", task_kind="generate_json", operation="execution_semantic"
    )
    result = SimpleNamespace(
        status="failed",
        error_code="invalid_provider_response",
        egress_audit=SimpleNamespace(
            profile_id="operational",
            provider="openai_compatible",
            model="test-model",
            status="failed",
            input_bytes=123,
            output_bytes=0,
        ),
    )

    worker._record_egress_audit(task, result, "space")

    connection = sqlite3.connect(database)
    row = connection.execute(
        "SELECT operation, provider_kind, model, status, request_bytes, "
        "response_bytes, attempts, error_code FROM egress_audit"
    ).fetchone()
    connection.close()
    assert row == (
        "execution_semantic",
        "openai_compatible",
        "test-model",
        "failed",
        123,
        0,
        1,
        "invalid_provider_response",
    )


def test_provider_configuration_codes_open_the_circuit() -> None:
    for code in (
        "authentication_error",
        "configuration_error",
        "provider_capability_unverified",
        "provider_secret_missing",
        "secret_missing",
    ):
        worker = CoreExecutionTaskWorker(
            database_path="unused.db",
            gateway=SimpleNamespace(),  # type: ignore[arg-type]
            executor=SimpleNamespace(),  # type: ignore[arg-type]
            worker_id="test-worker",
        )
        worker._open_provider_circuit_on_failure(
            SimpleNamespace(status="failed", error_code=code)
        )
        assert worker.provider_circuit_open is True


def test_decide_task_never_allows_provider_fallback() -> None:
    task = SimpleNamespace(
        task_kind="decide",
        decision_request={"schema_version": 2},
        operation_input={"resolution_pipeline": "kr"},
    )
    assert CoreExecutionTaskWorker._fallback_allowed(task) is False


def test_batch_failure_codes_stay_terminal_and_content_free() -> None:
    assert _batch_failure_code("provider_unavailable") == "batch_failed"
    assert _batch_failure_code("timeout") == "batch_failed"
    assert _batch_failure_code("schema_shape_failure") == "schema_shape_failure"
    assert _batch_failure_code("batch_result_missing") == "batch_result_missing"
    assert _batch_failure_code("provider said secret value") == "batch_failed"
