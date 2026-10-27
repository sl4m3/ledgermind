from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ledgermind_local.api.context import create_context_router
from ledgermind_local.core_gateway.contracts import (
    RecordRetrievalOutcomeCommand,
    RetrieveContextResult,
    TransientCoreError,
)
from ledgermind_local.core_gateway.queued_context import QueuedContextGateway
from ledgermind_local.persistence import open_sqlite_connection, rounds_migrations
from ledgermind_local.persistence.raw_round_repository import SQLiteRawRoundRepository
from ledgermind_local.scheduler.core_command_worker import CoreCommandWorker


def database(tmp_path: Path) -> Path:
    path = tmp_path / "rounds.db"
    connection = open_sqlite_connection(path)
    rounds_migrations.apply_migrations(connection)
    connection.close()
    return path


def outcome(*, request_id="http-1", value_id="v1"):
    return RecordRetrievalOutcomeCommand(
        request_id=request_id,
        retrieval_request_id="retrieval-1",
        candidate_value_ids=(value_id, "v2"),
        delivered_value_ids=(value_id,),
    )


class Gateway:
    def __init__(self, failures=0):
        self.failures = failures
        self.outcomes = []
        self.committed = set()

    def retrieve_context(self, request):
        return RetrieveContextResult(
            {
                "retrieval_request_id": "retrieval-1",
                "items": [
                    {
                        "value_id": "v1",
                        "primary_object_id": "o1",
                        "object_name": "Deployment",
                        "facet": "constraint",
                        "content": "Review before deployment.",
                        "relevance": 0.9,
                        "explanation": {
                            "object_reasons": ["direct_value_semantic"],
                            "item_facet": "constraint",
                            "activated_facets": [],
                            "score_components": {"semantic": 0.9},
                        },
                    }
                ],
            }
        )

    def record_retrieval_outcome(self, command):
        self.outcomes.append(command)
        self.committed.add(command.retrieval_request_id)
        if self.failures:
            self.failures -= 1
            raise TransientCoreError("simulated lost acknowledgement after Core commit")


def test_queue_is_durable_idempotent_and_scoped(tmp_path):
    path, gateway = database(tmp_path), Gateway()
    queued = QueuedContextGateway(gateway, path)
    first = queued.enqueue_retrieval_outcome("space-1", outcome())
    replay = QueuedContextGateway(gateway, path).enqueue_retrieval_outcome(
        "space-1",
        outcome(request_id="another-http-attempt"),
    )
    other = queued.enqueue_retrieval_outcome("space-2", outcome())
    assert first == replay != other
    assert not gateway.outcomes
    with pytest.raises(ValueError, match="payload conflict"):
        queued.enqueue_retrieval_outcome("space-1", outcome(value_id="different"))
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT status,payload_json FROM core_commands"
        ).fetchall()
        assert len(rows) == 2
        assert all(
            status == "pending" and "Review" not in payload for status, payload in rows
        )


def test_restart_delivers_original_event_time_and_no_duplicate_work(tmp_path):
    path, gateway = database(tmp_path), Gateway()
    command_id = QueuedContextGateway(gateway, path).enqueue_retrieval_outcome(
        "space", outcome()
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE core_commands SET created_at='2026-01-01T00:00:00+00:00'"
        )
    worker = CoreCommandWorker(database_path=path, gateway=gateway)
    assert worker.process_once().status == "completed"
    assert worker.process_once() is None
    assert gateway.outcomes[0].request_id == command_id
    assert gateway.outcomes[0].created_at == "2026-01-01T00:00:00+00:00"
    assert gateway.outcomes[0].candidate_value_ids == ("v1", "v2")
    assert gateway.outcomes[0].delivered_value_ids == ("v1",)


def test_lost_core_acknowledgement_replays_without_losing_event(tmp_path):
    path, gateway = database(tmp_path), Gateway(failures=1)
    QueuedContextGateway(gateway, path).enqueue_retrieval_outcome("space", outcome())
    worker = CoreCommandWorker(
        database_path=path, gateway=gateway, retry_delay_seconds=0
    )
    assert worker.process_once().status == "retry_wait"
    assert worker.process_once().status == "completed"
    assert len(gateway.outcomes) == 2
    assert len(gateway.committed) == 1
    assert gateway.outcomes[0] == gateway.outcomes[1]


def test_restart_reclaims_expired_lease(tmp_path):
    path, gateway = database(tmp_path), Gateway()
    QueuedContextGateway(gateway, path).enqueue_retrieval_outcome("space", outcome())
    connection = open_sqlite_connection(path)
    claimed = SQLiteRawRoundRepository(connection).claim_core_command(
        worker_id="crashed"
    )
    assert claimed is not None
    connection.execute(
        "UPDATE core_commands SET lease_expires_at='2000-01-01T00:00:00+00:00'"
    )
    connection.commit()
    connection.close()
    result = CoreCommandWorker(
        database_path=path, gateway=gateway, worker_id="recovered"
    ).process_once()
    assert result.status == "completed"


def test_exhausted_retries_keep_the_event_and_error(tmp_path):
    path, gateway = database(tmp_path), Gateway(failures=9)
    QueuedContextGateway(gateway, path).enqueue_retrieval_outcome("space", outcome())
    worker = CoreCommandWorker(
        database_path=path, gateway=gateway, max_attempts=2, retry_delay_seconds=0
    )
    assert worker.process_once().status == "retry_wait"
    assert worker.process_once().status == "failed"
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT status,attempts,payload_json,last_error_code FROM core_commands"
        ).fetchone()
        assert row[0:2] == ("failed", 2)
        assert "retrieval-1" in row[2] and row[3] == "core_delivery_error"


def test_invalid_outcome_is_rejected_not_interpreted_as_delivery(tmp_path):
    path, gateway = database(tmp_path), Gateway()
    QueuedContextGateway(gateway, path).enqueue_retrieval_outcome("space", outcome())
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE core_commands SET payload_json='{}'")
    result = CoreCommandWorker(database_path=path, gateway=gateway).process_once()
    assert result.status == "rejected"
    assert not gateway.outcomes


def test_http_returns_before_statistics_and_persists_the_selected_ids(tmp_path):
    path, gateway = database(tmp_path), Gateway(failures=99)
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token", QueuedContextGateway(gateway, path), max_body_bytes=100_000
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "memory_space_id": "space",
            "query": "deploy",
            "query_embedding": [0.1, 0.2],
        },
    )
    assert response.status_code == 200
    assert response.headers["X-LedgerMind-Usage-Status"] == "queued"
    assert response.json()["selection_diagnostics"]["stage"] == "service_selected"
    assert response.json()["selection_diagnostics"]["usage_status"] == "queued"
    assert not gateway.outcomes
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM core_commands WHERE status='pending'"
            ).fetchone()[0]
            == 1
        )


def test_unpersisted_outcome_does_not_get_a_successful_acknowledgement(tmp_path):
    class Unavailable(QueuedContextGateway):
        def enqueue_retrieval_outcome(self, *_args):
            raise OSError("outbox disk unavailable")

    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            Unavailable(Gateway(), database(tmp_path)),
            max_body_bytes=100_000,
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "memory_space_id": "space",
            "query": "deploy",
            "query_embedding": [0.1, 0.2],
        },
    )
    assert response.status_code == 503
