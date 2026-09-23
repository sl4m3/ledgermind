from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from ledgermind_local.core_gateway.contracts import DomainRejectedError
from ledgermind_local.scheduler import core_execution_task_worker as worker_module
from ledgermind_local.scheduler.core_execution_task_worker import (
    CoreExecutionTaskWorker,
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

    monkeypatch.setattr(worker_module.migrations, "apply_migrations", lambda _connection: None)
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
        grounding.error_code
        == "core_rejected_round_semantic_object_grounding_missing"
    )
    assert (
        unknown_object.error_code
        == "core_rejected_round_semantic_claim_object_unknown"
    )
    assert "o2" not in grounding.error_code
    assert "o9" not in unknown_object.error_code


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

    assert calls == [{"force_provider_fallback": True}]
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

    assert calls == [{"force_provider_fallback": True}]
    assert deliveries == 2


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
