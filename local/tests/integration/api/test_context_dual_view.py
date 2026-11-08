from __future__ import annotations

import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledgermind_local.api.context import create_context_router
from ledgermind_local.config import RetrievalConfig
from ledgermind_local.core_gateway.contracts import (
    RecordRetrievalOutcomeCommand,
    RetrieveContextCommand,
    RetrieveContextResult,
)


def _item(value_id: str, content: str) -> dict[str, object]:
    return {
        "value_id": value_id,
        "primary_object_id": "object-1",
        "object_name": "Deployment",
        "facet": "state",
        "content": content,
        "source_kind": "explicit_user",
        "relevance": 0.5,
        "explanation": {
            "object_reasons": ["direct_value_semantic"],
            "item_facet": "state",
            "activated_facets": [],
            "score_components": {
                "semantic": 0.5,
                "object": 0.0,
                "facet": 0.0,
                "scope_time": 0.0,
                "context": 0.0,
                "recency": 0.0,
                "support": 0.0,
                "usage": 0.0,
            },
        },
    }


class _Gateway:
    def __init__(self) -> None:
        self.requests: list[RetrieveContextCommand] = []
        self.outcomes: list[RecordRetrievalOutcomeCommand] = []

    def retrieve_context(
        self, request: RetrieveContextCommand
    ) -> RetrieveContextResult:
        self.requests.append(request)
        value_id = (
            "value-context"
            if "Session says beta" in request.query_text
            else "value-primary"
        )
        return RetrieveContextResult(
            {
                "schema_version": 2,
                "retrieval_request_id": f"retrieval-{len(self.requests)}",
                "items": [
                    _item("alpha", "alpha fact"),
                    _item("beta", "beta fact"),
                    _item("gamma", "gamma fact"),
                ],
                "memory_injection": {
                    "format": "facet_legend",
                    "text": (
                        "How to read memory:\n"
                        "state — a stable characteristic.\n\n"
                        f"M1: [state] Deployment: fact from {value_id}."
                    ),
                    "legend": ["state — a stable characteristic."],
                    "item_count": 3,
                },
            }
        )

    def record_retrieval_outcome(self, command: RecordRetrievalOutcomeCommand) -> None:
        self.outcomes.append(command)


class _Embedder:
    def embed_query_with_metadata(
        self, memory_space_id: str, query: str
    ) -> tuple[tuple[float, ...], str, str]:
        del memory_space_id, query
        return (0.1, 0.2), "embedder", "2026-08"

    def embed_object_query_with_metadata(
        self, memory_space_id: str, query: str
    ) -> tuple[tuple[float, ...], str, str]:
        del memory_space_id, query
        return (0.3, 0.4), "embedder", "2026-08"


class _Reranker:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.queries: list[str] = []

    def score(self, query: str, documents: list[str]) -> list[float]:
        self.queries.append(query)
        if self.fail_on is not None and self.fail_on in query:
            raise RuntimeError("view failed")
        if "Recent session context" in query:
            return [0.9 if "beta" in document else 0.1 for document in documents]
        if "Task asks alpha" in query:
            return [0.9 if "alpha" in document else 0.1 for document in documents]
        return [0.5 for _ in documents]


def _session_database(tmp_path):
    database = tmp_path / "knowledge.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE raw_rounds ("
            "raw_round_id TEXT PRIMARY KEY, memory_space_id TEXT, payload_json TEXT)"
        )
        payload = {
            "events": [
                {
                    "event_id": "a1",
                    "sequence": 0,
                    "kind": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Session says beta."}],
                }
            ]
        }
        connection.execute(
            "INSERT INTO raw_rounds VALUES ('r1', 'space', ?)",
            (json.dumps(payload),),
        )
    return database


def _client(database, *, reranker=None, retrieval=None):
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            _Gateway(),
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
            reranker=reranker or _Reranker(),
            session_context_database_path=database,
            retrieval_config=retrieval or RetrievalConfig(),
        )
    )
    return TestClient(app)


def test_dual_view_scores_task_and_context_and_fuses_by_max(tmp_path) -> None:
    reranker = _Reranker()
    response = _client(_session_database(tmp_path), reranker=reranker).post(
        "/context/retrieve",
        json={
            "schema_version": 2,
            "memory_space_id": "space",
            "query": "Task asks alpha",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(reranker.queries) == 2
    assert "Task asks alpha" in reranker.queries[0]
    assert "Recent session context" in reranker.queries[1]
    diagnostics = payload["selection_diagnostics"]
    assert diagnostics["rerank_views"] == ["task", "context"]
    assert diagnostics["session_context_query_truncated"] is False
    ranking = {row["value_id"]: row for row in diagnostics["ranking"]}
    assert (
        ranking["alpha"]["view_scores"]["task"]
        > ranking["alpha"]["view_scores"]["context"]
    )
    assert (
        ranking["beta"]["view_scores"]["context"]
        > ranking["beta"]["view_scores"]["task"]
    )
    assert ranking["alpha"]["best_view"] == "task"
    assert ranking["beta"]["best_view"] == "context"


def test_without_session_context_only_one_view_is_scored(tmp_path) -> None:
    reranker = _Reranker()
    database = tmp_path / "empty.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE raw_rounds ("
            "raw_round_id TEXT PRIMARY KEY, memory_space_id TEXT, payload_json TEXT)"
        )

    response = _client(database, reranker=reranker).post(
        "/context/retrieve",
        json={
            "schema_version": 2,
            "memory_space_id": "space",
            "query": "Task asks alpha",
        },
    )

    assert response.status_code == 200
    assert len(reranker.queries) == 1
    assert response.json()["selection_diagnostics"]["rerank_views"] == []


def test_context_view_failure_falls_back_to_task_view(tmp_path) -> None:
    response = _client(
        _session_database(tmp_path),
        reranker=_Reranker(fail_on="Recent session context"),
    ).post(
        "/context/retrieve",
        json={
            "schema_version": 2,
            "memory_space_id": "space",
            "query": "Task asks alpha",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selection_diagnostics"]["status"] == "reranked"
    assert payload["selection_diagnostics"]["rerank_views"] == ["task"]
    assert payload["selection_diagnostics"]["rerank_fallback"] == "task_view"


def test_both_views_failure_falls_back_to_core_order(tmp_path) -> None:
    response = _client(
        _session_database(tmp_path),
        reranker=_Reranker(fail_on="Task asks alpha"),
    ).post(
        "/context/retrieve",
        json={
            "schema_version": 2,
            "memory_space_id": "space",
            "query": "Task asks alpha",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selection_diagnostics"]["status"] == "core_fallback"
    assert response.headers["X-LedgerMind-Selection"] == "core_fallback"


def test_secondary_context_is_truncated_before_retrieval(tmp_path) -> None:
    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
            reranker=_Reranker(),
            session_context_database_path=_session_database(tmp_path),
            retrieval_config=RetrievalConfig(session_context_query_chars=13),
        )
    )

    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "schema_version": 2,
            "memory_space_id": "space",
            "query": "Task asks alpha",
        },
    )

    assert response.status_code == 200
    secondary = gateway.requests[1].query_text
    assert secondary == "Session says"
    diagnostics = response.json()["selection_diagnostics"]
    assert diagnostics["session_context_query_truncated"] is True
    assert diagnostics["session_context_query_chars"] == len("Session says")


def test_disabling_dual_view_uses_only_context_view(tmp_path) -> None:
    reranker = _Reranker()
    response = _client(
        _session_database(tmp_path),
        reranker=reranker,
        retrieval=RetrievalConfig(dual_view_rerank=False),
    ).post(
        "/context/retrieve",
        json={
            "schema_version": 2,
            "memory_space_id": "space",
            "query": "Task asks alpha",
        },
    )

    assert response.status_code == 200
    assert len(reranker.queries) == 1
    assert "Recent session context" in reranker.queries[0]
    assert response.json()["selection_diagnostics"]["rerank_views"] == ["context"]


def test_disabling_adaptive_merge_uses_interleave(tmp_path) -> None:
    response = _client(
        _session_database(tmp_path),
        retrieval=RetrievalConfig(adaptive_merge=False),
    ).post(
        "/context/retrieve",
        json={"schema_version": 2, "memory_space_id": "space", "query": "давай"},
    )

    assert response.status_code == 200
    assert response.json()["selection_diagnostics"]["merge_policy"] == "interleave"


def test_zero_context_cap_disables_truncation(tmp_path) -> None:
    response = _client(
        _session_database(tmp_path),
        retrieval=RetrievalConfig(session_context_query_chars=0),
    ).post(
        "/context/retrieve",
        json={
            "schema_version": 2,
            "memory_space_id": "space",
            "query": "Task asks alpha",
        },
    )

    assert response.status_code == 200
    diagnostics = response.json()["selection_diagnostics"]
    assert diagnostics["session_context_query_truncated"] is False
    assert diagnostics["session_context_query_chars"] == len("Session says beta.")


def test_full_aspect_pool_skips_session_chunk_retrieval(tmp_path) -> None:
    class Gateway(_Gateway):
        def __init__(self) -> None:
            super().__init__()
            self.queries: list[str] = []

        def retrieve_context(self, request):
            self.queries.append(request.query_text)
            prefix = {
                "alpha width, beta background and gamma delay": "full",
                "alpha width": "aspect-0",
                "beta background": "aspect-1",
                "gamma delay": "aspect-2",
            }[request.query_text]
            return RetrieveContextResult(
                {
                    "schema_version": 2,
                    "retrieval_request_id": f"retrieval-{len(self.queries)}",
                    "items": [
                        _item(f"{prefix}-{index}", f"{prefix} fact {index}")
                        for index in range(32)
                    ],
                    "memory_injection": {
                        "format": "facet_legend",
                        "text": "How to read memory:\nstate — a stable characteristic.",
                        "legend": ["state — a stable characteristic."],
                        "item_count": 32,
                    },
                }
            )

    gateway = Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
            reranker=_Reranker(),
            session_context_database_path=_session_database(tmp_path),
            retrieval_config=RetrievalConfig(),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "schema_version": 2,
            "memory_space_id": "space",
            "query": "alpha width, beta background and gamma delay",
        },
    )

    assert response.status_code == 200
    assert gateway.queries == [
        "alpha width, beta background and gamma delay",
        "alpha width",
        "beta background",
        "gamma delay",
    ]
    diagnostics = response.json()["selection_diagnostics"]
    assert diagnostics["session_context_chunks"] == 0
    assert diagnostics["session_context_candidates"] == 0
    assert diagnostics["session_context_retrieval_skipped"] is True
    assert diagnostics["rerank_views"] == [
        "task",
        "aspect:0",
        "aspect:1",
        "aspect:2",
        "context",
    ]
