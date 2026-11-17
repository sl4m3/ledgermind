from __future__ import annotations

import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledgermind_local.api.context import create_context_router
from ledgermind_local.core_gateway.contracts import (
    RecordRetrievalOutcomeCommand,
    RetrieveContextCommand,
    RetrieveContextResult,
)


class _Gateway:
    def __init__(self) -> None:
        self.request: RetrieveContextCommand | None = None
        self.outcomes: list[RecordRetrievalOutcomeCommand] = []

    def retrieve_context(
        self, request: RetrieveContextCommand
    ) -> RetrieveContextResult:
        self.request = request
        schema_version = (
            5 if request.scoped_dependencies else 4 if request.semantic_delivery else 2
        )
        item: dict[str, object] = {
            "value_id": "value-1",
            "primary_object_id": "object-1",
            "object_name": "Deployment",
            "facet": "property",
            "content": "Deployments require review.",
            "source_kind": "explicit_user",
            "relevance": 0.9,
            "explanation": {
                "object_reasons": ["direct_value_semantic"],
                "item_facet": "property",
                "activated_facets": [],
                "score_components": {
                    "semantic": 0.9,
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
        injection: dict[str, object] = {
            "format": "facet_legend",
            "text": "How to read memory:\nproperty — a stable characteristic.\n\nM1: [property] Deployment: Deployments require review.",
            "legend": ["property — a stable characteristic."],
            "item_count": 1,
        }
        if request.semantic_delivery:
            item["semantic_safety"] = {
                "dependencies": [],
                "scope_checks": [],
            }
            item["requires_revalidation"] = False
            injection["format"] = "semantic_units"
            injection["semantic_contract_version"] = "memory_semantics"
        return RetrieveContextResult(
            {
                "schema_version": schema_version,
                "retrieval_request_id": "retrieval-1",
                "items": [item],
                "memory_injection": injection,
            }
        )

    def record_retrieval_outcome(self, command: RecordRetrievalOutcomeCommand) -> None:
        self.outcomes.append(command)


class _Embedder:
    def embed_query_with_metadata(
        self, memory_space_id: str, query: str
    ) -> tuple[tuple[float, ...], str, str]:
        assert memory_space_id == "space"
        assert query == "deployment"
        return (0.1, 0.2), "embedder", "2026-08"

    def embed_object_query_with_metadata(
        self, memory_space_id: str, query: str
    ) -> tuple[tuple[float, ...], str, str]:
        assert memory_space_id == "space"
        assert query == "deployment"
        return (0.3, 0.4), "embedder", "2026-08"


def test_context_embeds_query_returns_provenance_and_records_outcome() -> None:
    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
        )
    )

    response = TestClient(app).post(
        "/context/retrieve",
        headers={"X-Request-ID": "request-1"},
        json={
            "memory_space_id": "space",
            "query": "deployment",
            "project_id": "project-1",
            "repository_id": "repository-1",
            "task_id": "task-1",
            "conversation_id": "conversation-1",
            "visible_value_ids": ["already-shown"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 2
    assert payload["retrieval_request_id"] == "retrieval-1"
    assert payload["delivered_value_ids"] == ["value-1"]
    assert payload["items"][0]["object_name"] == "Deployment"
    assert payload["items"][0]["facet"] == "property"
    assert payload["memory_injection"]["format"] == "facet_legend"
    assert payload["memory_injection"]["item_count"] == 1
    assert "source_kind" not in payload["items"][0]
    assert payload["items"][0]["explanation"]["object_reasons"] == [
        "direct_value_semantic"
    ]
    assert gateway.request is not None
    assert gateway.request.query_embedding == (0.1, 0.2)
    assert gateway.request.object_query_embedding == (0.3, 0.4)
    assert gateway.request.embedding_model_id == "embedder"
    assert gateway.request.repository_id == "repository-1"
    assert gateway.request.visible_value_ids == ("already-shown",)
    assert gateway.request.candidate_policy == "formula"
    assert payload["selection_diagnostics"]["candidate_policy"] == "formula"
    assert payload["selection_diagnostics"]["selection_mode"] == (
        "formula_topk_no_reranker"
    )
    assert gateway.outcomes[0].candidate_value_ids == ("value-1",)
    assert gateway.outcomes[0].delivered_value_ids == ("value-1",)


def test_injection_event_receipt_is_idempotent_and_distinct_from_selection() -> None:
    app = FastAPI()
    app.include_router(
        create_context_router(lambda: "token", _Gateway(), max_body_bytes=100_000)
    )
    payload = {
        "event_id": "event-1",
        "retrieval_request_id": "retrieval-1",
        "memory_space_id": "space",
        "session_id": "session-1",
        "stage": "hook_returned_assumed_visible",
        "value_ids": ["value-1"],
    }
    first = TestClient(app).post("/context/injection-events", json=payload)
    second = TestClient(app).post("/context/injection-events", json=payload)
    assert first.status_code == second.status_code == 202
    assert (
        first.json() == second.json() == {"status": "accepted", "event_id": "event-1"}
    )


def test_visible_value_ids_reject_duplicates_before_core() -> None:
    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "memory_space_id": "space",
            "query": "deployment",
            "visible_value_ids": ["value-1", "value-1"],
        },
    )
    assert response.status_code == 422
    assert gateway.request is None


def test_optional_reranker_uses_core_pool_and_records_only_injected_values() -> None:
    class Gateway(_Gateway):
        def retrieve_context(
            self, request: RetrieveContextCommand
        ) -> RetrieveContextResult:
            assert request.limit == 32
            assert request.candidate_policy == "semantic"
            original = super().retrieve_context(request).payload
            original["items"] = [
                {
                    **original["items"][0],
                    "value_id": f"value-{index}",
                    "content": f"Rule {index}.",
                }
                for index in range(1, 9)
            ]
            original["memory_injection"]["item_count"] = 8
            return RetrieveContextResult(original)

    class Reranker:
        def score(self, query: str, documents: list[str]) -> list[float]:
            assert len(documents) == 8
            return [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.1, 0.05]

    gateway = Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
            reranker=Reranker(),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={"schema_version": 5, "memory_space_id": "space", "query": "deployment"},
    )
    assert response.status_code == 200
    assert response.headers["X-LedgerMind-Selection"] == "reranked"
    payload = response.json()
    assert len(payload["items"]) == 6
    assert payload["selection_diagnostics"]["selection_policy"] == "adaptive_k"
    assert payload["selection_diagnostics"]["candidate_policy"] == "semantic"
    assert payload["selection_diagnostics"]["selection_mode"] == (
        "semantic_top32_reranked"
    )
    assert payload["selection_diagnostics"]["adaptive_k_cutoff"] == 6
    assert [item["value_id"] for item in payload["items"]] == [
        "value-1",
        "value-2",
        "value-3",
        "value-4",
        "value-5",
        "value-6",
    ]
    assert payload["delivered_value_ids"] == [
        item["value_id"] for item in payload["items"]
    ]
    assert payload["selection_diagnostics"]["status"] == "reranked"
    assert payload["selection_diagnostics"]["candidate_count"] == 8
    assert len(gateway.outcomes[0].candidate_value_ids) == 8
    assert payload["selection_diagnostics"]["ranking"][0]["value_id"] == "value-1"
    assert (
        round(payload["selection_diagnostics"]["ranking"][0]["reranker_score"], 3)
        == 0.9
    )
    assert (
        payload["selection_diagnostics"]["injection_size_unit"]
        == "word_punctuation_units"
    )
    assert payload["selection_diagnostics"]["estimated_injection_tokens"] is None
    assert (
        payload["selection_diagnostics"]["injection_rendering"]
        == "object_facet_groups_v1"
    )
    assert payload["selection_diagnostics"]["injection_group_count"] == 1
    assert payload["selection_diagnostics"]["injection_claim_count"] == len(
        payload["items"]
    )
    assert payload["memory_injection"]["item_count"] == len(payload["items"])
    assert payload["memory_injection"]["text"].count("[property] Deployment") == 1
    assert gateway.outcomes[0].delivered_value_ids == tuple(
        payload["delivered_value_ids"]
    )


def test_reranker_failure_uses_core_order() -> None:
    class Broken:
        def score(self, query: str, documents: list[str]) -> list[float]:
            raise RuntimeError("unavailable")

    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
            reranker=Broken(),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={"schema_version": 5, "memory_space_id": "space", "query": "deployment"},
    )
    assert response.status_code == 200
    assert response.headers["X-LedgerMind-Selection"] == "core_fallback"
    assert response.json()["delivered_value_ids"] == ["value-1"]
    assert response.json()["selection_diagnostics"]["fallback_reason"] == "RuntimeError"
    assert gateway.request is not None
    assert gateway.request.candidate_policy == "semantic"
    assert response.json()["selection_diagnostics"]["selection_mode"] == (
        "semantic_top32_reranked"
    )


def test_formula_override_with_reranker_preserves_baseline_mode() -> None:
    from types import SimpleNamespace

    class Reranker:
        def score(self, query: str, documents: list[str]) -> list[float]:
            return [0.5 for _ in documents]

    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
            reranker=Reranker(),
            reranker_config=SimpleNamespace(
                candidate_policy="formula",
                soft_budget=100_000,
                selection_policy="adaptive_k",
            ),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={"schema_version": 5, "memory_space_id": "space", "query": "deployment"},
    )
    assert response.status_code == 200
    assert gateway.request is not None
    assert gateway.request.candidate_policy == "formula"
    assert gateway.request.limit == 32
    assert response.json()["selection_diagnostics"]["candidate_policy"] == "formula"
    assert response.json()["selection_diagnostics"]["selection_mode"] == (
        "formula_top32_reranked"
    )


def test_legacy_schema_with_reranker_keeps_formula_policy() -> None:
    class Reranker:
        def score(self, query: str, documents: list[str]) -> list[float]:
            return [0.5 for _ in documents]

    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
            reranker=Reranker(),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={"schema_version": 2, "memory_space_id": "space", "query": "deployment"},
    )
    assert response.status_code == 200
    assert gateway.request is not None
    assert gateway.request.candidate_policy == "formula"
    assert gateway.request.limit == 32
    assert gateway.request.to_payload()["schema_version"] == 2
    assert "candidate_policy" not in gateway.request.to_payload()
    assert response.json()["selection_diagnostics"]["selection_mode"] == (
        "formula_top32_reranked"
    )


def test_internal_core_dependency_links_survive_public_context_projection():
    from types import SimpleNamespace

    class Gateway(_Gateway):
        def retrieve_context(self, request):
            assert request.explanation_level == "compact"
            original = super().retrieve_context(request).payload
            original["items"] = [
                {
                    **original["items"][0],
                    "value_id": f"value-{i}",
                    "content": f"Rule {i}.",
                }
                for i in range(1, 9)
            ]
            original["retrieval_diagnostics"] = {
                "pipeline": {
                    "dependency_links": {"value-1": ["value-7"], "value-7": ["value-8"]}
                }
            }
            original["memory_injection"]["item_count"] = 8
            return RetrieveContextResult(original)

    class Reranker:
        def score(self, query, documents):
            return [8, 7, 6, 5, 4, 3, 0, 0]

    app = FastAPI()
    gateway = Gateway()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100000,
            query_embedder=_Embedder(),
            reranker=Reranker(),
            reranker_config=SimpleNamespace(
                soft_budget=100_000, selection_policy="adaptive_k"
            ),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve", json={"memory_space_id": "space", "query": "deployment"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["delivered_value_ids"] == [f"value-{i}" for i in range(1, 8)]
    assert payload["selection_diagnostics"]["dependency_value_ids"] == ["value-7"]
    assert "retrieval_diagnostics" not in payload


def test_host_request_time_is_forwarded_to_core():
    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "memory_space_id": "space",
            "query": "deployment",
            "request_time": "2026-10-31T12:00:00Z",
        },
    )
    assert response.status_code == 200
    assert gateway.request is not None
    assert gateway.request.request_time == "2026-10-31T12:00:00Z"


def test_host_schema_five_selects_semantic_delivery_and_scoped_dependencies():
    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=_Embedder(),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "memory_space_id": "space",
            "query": "deployment",
            "schema_version": 5,
        },
    )
    assert response.status_code == 200
    assert gateway.request is not None
    assert gateway.request.semantic_delivery is True
    assert gateway.request.scoped_dependencies is True
    assert gateway.request.to_payload()["schema_version"] == 5


def test_host_task_context_is_identical_for_embeddings_core_and_reranker():
    queries = []

    class Embedder:
        def embed_query(self, space, query):
            queries.append(query)
            return (0.1, 0.2)

    class Reranker:
        def score(self, query, documents):
            queries.append(query)
            return [0.8] * len(documents)

    gateway = _Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100000,
            query_embedder=Embedder(),
            reranker=Reranker(),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "memory_space_id": "space",
            "query": "continue",
            "query_context": "Release service",
            "conversation_id": "session",
        },
    )
    assert response.status_code == 200
    assert queries[0] == queries[1] == gateway.request.query_text
    assert "Release service" in queries[0]
    assert gateway.request.conversation_id == "session"


def test_packing_failure_never_returns_entire_candidate_pool():
    class Gateway(_Gateway):
        def retrieve_context(self, request):
            original = super().retrieve_context(request).payload
            original["items"] = [
                {
                    **original["items"][0],
                    "value_id": f"v{i}",
                    "content": f"Deployments require review {i}.",
                }
                for i in range(32)
            ]
            original["memory_injection"]["item_count"] = 32
            return RetrieveContextResult(original)

    class Reranker:
        def score(self, query, documents):
            return [0.5] * len(documents)

        def count_tokens(self, text):
            raise RuntimeError("tokenizer worker unavailable")

    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            Gateway(),
            max_body_bytes=100000,
            query_embedder=_Embedder(),
            reranker=Reranker(),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve", json={"memory_space_id": "space", "query": "deployment"}
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 5
    assert response.json()["memory_injection"] is None


def test_session_context_is_embedded_retrieved_and_used_for_reranking(tmp_path) -> None:
    database = tmp_path / "rounds.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE raw_rounds (raw_round_id TEXT PRIMARY KEY, memory_space_id TEXT, payload_json TEXT)"
        )
        connection.execute(
            "CREATE TABLE raw_round_payloads (raw_round_id TEXT PRIMARY KEY, payload_json TEXT)"
        )
        payload = {
            "round": {
                "events": [
                    {
                        "event_id": "a1",
                        "sequence": 0,
                        "kind": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "The deployment requires a security review before release.",
                            }
                        ],
                    }
                ]
            }
        }
        connection.execute("INSERT INTO raw_rounds VALUES ('r1', 'space', '{}')")
        connection.execute(
            "INSERT INTO raw_round_payloads VALUES ('r1', ?)",
            (json.dumps(payload),),
        )

    class Gateway(_Gateway):
        def __init__(self) -> None:
            super().__init__()
            self.requests: list[RetrieveContextCommand] = []

        def retrieve_context(
            self, request: RetrieveContextCommand
        ) -> RetrieveContextResult:
            self.requests.append(request)
            original = super().retrieve_context(request).payload
            value_id = (
                "value-context"
                if "security review" in request.query_text
                else "value-primary"
            )
            original["items"] = [
                {
                    **original["items"][0],
                    "value_id": value_id,
                    "content": f"Fact from {value_id}.",
                }
            ]
            return RetrieveContextResult(original)

    class Embedder:
        def embed_query_with_metadata(self, memory_space_id: str, query: str):
            del memory_space_id, query
            return (0.1, 0.2), "embedder", "2026-08"

        def embed_object_query_with_metadata(self, memory_space_id: str, query: str):
            del memory_space_id, query
            return (0.3, 0.4), "embedder", "2026-08"

    class Reranker:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def score(self, query: str, documents: list[str]) -> list[float]:
            self.queries.append(query)
            return [0.9 for _ in documents]

    gateway = Gateway()
    reranker = Reranker()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=Embedder(),
            reranker=reranker,
            session_context_database_path=database,
        )
    )

    response = TestClient(app).post(
        "/context/retrieve",
        json={"schema_version": 5, "memory_space_id": "space", "query": "давай"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(gateway.requests) == 2
    assert all(request.candidate_policy == "semantic" for request in gateway.requests)
    assert "security review" in gateway.requests[1].query_text
    assert len(reranker.queries) == 2
    assert "давай" in reranker.queries[0]
    assert any("security review" in query for query in reranker.queries)
    assert payload["selection_diagnostics"]["rerank_views"] == ["task", "context"]
    assert payload["selection_diagnostics"]["session_context_chars"] > 0
    assert payload["selection_diagnostics"]["session_context_chunks"] == 1
    assert payload["selection_diagnostics"]["session_context_candidates"] == 1
    assert {item["value_id"] for item in payload["items"]} == {
        "value-primary",
        "value-context",
    }


def test_multi_aspect_quota_retrieves_each_explicit_aspect() -> None:
    from types import SimpleNamespace

    class Gateway(_Gateway):
        def __init__(self) -> None:
            super().__init__()
            self.queries: list[str] = []

        def retrieve_context(self, request):
            self.queries.append(request.query_text)
            original = super().retrieve_context(request).payload
            if (
                request.query_text
                == "deployment width, collapsed background and delay after restart"
            ):
                ids = ["full-1", "full-2"]
            else:
                index = len(
                    [
                        q
                        for q in self.queries
                        if q
                        != "deployment width, collapsed background and delay after restart"
                    ]
                )
                ids = [f"aspect-{index}-{row}" for row in range(1, 4)]
            original["items"] = [
                {
                    **original["items"][0],
                    "value_id": value_id,
                    "content": f"Fact {value_id}.",
                }
                for value_id in ids
            ]
            original["memory_injection"]["item_count"] = len(ids)
            return RetrieveContextResult(original)

    class Embedder:
        def embed_query_with_metadata(self, memory_space_id, query):
            assert memory_space_id == "space"
            return (0.1, 0.2), "embedder", "2026-08"

        def embed_object_query_with_metadata(self, memory_space_id, query):
            assert memory_space_id == "space"
            return (0.3, 0.4), "embedder", "2026-08"

    class Reranker:
        def score(self, query, documents):
            return [0.9 - index * 0.01 for index in range(len(documents))]

    gateway = Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=Embedder(),
            reranker=Reranker(),
            reranker_config=SimpleNamespace(
                soft_budget=100_000,
                selection_policy="adaptive_k",
                candidate_policy="semantic",
            ),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "memory_space_id": "space",
            "query": "deployment width, collapsed background and delay after restart",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(gateway.queries) == 4
    assert payload["selection_diagnostics"]["aspect_query_count"] == 3
    assert payload["selection_diagnostics"]["aspect_candidate_count"] >= 8
    assert payload["selection_diagnostics"]["multi_aspect_quota"] is True
    assert "aspect:0" in payload["selection_diagnostics"]["rerank_views"]
    ranking_ids = {
        row["value_id"] for row in payload["selection_diagnostics"]["ranking"]
    }
    assert any(value_id.startswith("aspect-") for value_id in ranking_ids)


def test_multi_aspect_uses_one_batched_query_embedding_call() -> None:
    from types import SimpleNamespace

    full_query = "deployment width, collapsed background and delay after restart"

    class Gateway(_Gateway):
        def __init__(self) -> None:
            super().__init__()
            self.queries: list[str] = []
            self.limits: list[int] = []
            self.embeddings: list[tuple[float, ...]] = []

        def retrieve_context(self, request):
            self.queries.append(request.query_text)
            self.limits.append(request.limit)
            self.embeddings.append(tuple(request.query_embedding))
            original = super().retrieve_context(request).payload
            if request.query_text == full_query:
                ids = ["full-1", "full-2"]
            else:
                aspect_index = len(
                    [query for query in self.queries if query != full_query]
                )
                ids = [f"aspect-{aspect_index}-{row}" for row in range(1, 4)]
            original["items"] = [
                {
                    **original["items"][0],
                    "value_id": value_id,
                    "content": f"Fact {value_id}.",
                }
                for value_id in ids
            ]
            original["memory_injection"]["item_count"] = len(ids)
            return RetrieveContextResult(original)

    class BatchEmbedder:
        def __init__(self) -> None:
            self.batch_texts: list[str] | None = None

        def embed_query_batch_with_metadata(self, memory_space_id, texts):
            assert memory_space_id == "space"
            self.batch_texts = list(texts)
            return [
                ((float(index), 0.0), (0.0, float(index)), "embedder", "2026-08")
                for index, _ in enumerate(texts)
            ]

        def embed_query_with_metadata(self, memory_space_id, query):
            raise AssertionError("per-text query embedding must not be used")

        def embed_object_query_with_metadata(self, memory_space_id, query):
            raise AssertionError("per-text object embedding must not be used")

    class Reranker:
        def score(self, query, documents):
            return [0.9 - index * 0.01 for index in range(len(documents))]

    gateway = Gateway()
    embedder = BatchEmbedder()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=embedder,
            reranker=Reranker(),
            reranker_config=SimpleNamespace(
                soft_budget=100_000,
                selection_policy="adaptive_k",
                candidate_policy="semantic",
            ),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={"memory_space_id": "space", "query": full_query},
    )

    assert response.status_code == 200
    assert embedder.batch_texts == [
        full_query,
        "deployment width",
        "collapsed background",
        "delay after restart",
    ]
    assert gateway.queries[0] == full_query
    assert gateway.limits == [32, 8, 8, 8]
    assert gateway.embeddings == [
        (0.0, 0.0),
        (1.0, 0.0),
        (2.0, 0.0),
        (3.0, 0.0),
    ]
    assert len(gateway.queries) == 4
    payload = response.json()
    assert payload["selection_diagnostics"]["aspect_query_count"] == 3
    assert payload["selection_diagnostics"]["aspect_candidate_count"] >= 8


def test_multi_aspect_uses_adaptive_k_and_allows_more_than_15_items() -> None:
    from types import SimpleNamespace

    full_query = "dispatcher slice, its entrypoint and production activation status"

    class Gateway(_Gateway):
        def retrieve_context(self, request):
            original = super().retrieve_context(request).payload
            if request.query_text == full_query:
                ids = [f"item-{i}" for i in range(1, 25)]
            else:
                ids = [f"item-{i}" for i in range(1, 5)]
            original["items"] = [
                {
                    **original["items"][0],
                    "value_id": value_id,
                    "content": f"Fact {value_id}.",
                    "relevance": 0.5 - idx * 0.01,
                }
                for idx, value_id in enumerate(ids)
            ]
            original["memory_injection"]["item_count"] = len(ids)
            return RetrieveContextResult(original)

    class BatchEmbedder:
        def embed_query_batch_with_metadata(self, memory_space_id, texts):
            assert memory_space_id == "space"
            return [
                ((float(index), 0.0), (0.0, float(index)), "embedder", "2026-08")
                for index, _ in enumerate(texts)
            ]

    class Reranker:
        def score(self, query, documents):
            if query == full_query:
                # 18 relevant items tightly clustered high, then a sharp drop.
                return [
                    4.0 - index * 0.02 if index < 18 else -3.0 - index * 0.1
                    for index in range(len(documents))
                ]
            # Dead aspect queries score near-zero across all candidates.
            return [-4.0 for _ in documents]

    gateway = Gateway()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            gateway,
            max_body_bytes=100_000,
            query_embedder=BatchEmbedder(),
            reranker=Reranker(),
            reranker_config=SimpleNamespace(
                soft_budget=100_000,
                selection_policy="adaptive_k",
                candidate_policy="semantic",
            ),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={"memory_space_id": "space", "query": full_query},
    )

    assert response.status_code == 200
    payload = response.json()
    diag = payload["selection_diagnostics"]
    assert diag["aspect_query_count"] == 3
    assert diag["selection_policy"] == "adaptive_k"
    assert diag["adaptive_k_cutoff"] == 18
    assert len(payload["items"]) == 18
    scores = [row["reranker_score"] for row in diag["ranking"]]
    assert scores == sorted(scores, reverse=True)


def test_multi_aspect_reranker_failure_degrades_to_core_fallback() -> None:
    from types import SimpleNamespace

    full_query = (
        "What is the authorized next dispatcher slice, "
        "its entrypoint and production activation status?"
    )

    class BatchEmbedder:
        def embed_query_batch_with_metadata(self, memory_space_id, texts):
            assert memory_space_id == "space"
            return [
                ((float(index), 0.0), (0.0, float(index)), "embedder", "2026-08")
                for index, _ in enumerate(texts)
            ]

    class FailingReranker:
        def score(self, query, documents):
            raise RuntimeError("reranker unavailable")

    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            _Gateway(),
            max_body_bytes=100_000,
            query_embedder=BatchEmbedder(),
            reranker=FailingReranker(),
            reranker_config=SimpleNamespace(
                soft_budget=100_000,
                selection_policy="adaptive_k",
                candidate_policy="semantic",
            ),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={"memory_space_id": "space", "query": full_query},
    )

    assert response.status_code == 200
    assert response.headers["X-LedgerMind-Selection"] == "core_fallback"
    diag = response.json()["selection_diagnostics"]
    assert diag["status"] == "core_fallback"
    assert diag["selection_policy"] == "hybrid"
    assert diag["aspect_query_count"] == 3


def test_merged_pools_exclude_visible_ids_and_duplicate_claim_projections() -> None:
    from types import SimpleNamespace

    class MultiAspectDuplicateGateway(_Gateway):
        def retrieve_context(
            self, request: RetrieveContextCommand
        ) -> RetrieveContextResult:
            template = dict(super().retrieve_context(request).payload["items"][0])
            self.request = request
            is_aspect = ":aspect:" in (request.request_id or "")
            items = [
                {
                    **template,
                    "value_id": "v-primary",
                    "primary_object_id": "object-1",
                    "object_name": "Deployment",
                    "facet": "property",
                    "content": "Deployments require review.",
                    "relevance": 0.9,
                },
                {
                    **template,
                    "value_id": "v-already-visible",
                    "primary_object_id": "object-1",
                    "object_name": "Deployment",
                    "facet": "property",
                    "content": "Visible claim must not pass.",
                    "relevance": 0.8,
                },
            ]
            if is_aspect:
                items = [
                    {
                        **template,
                        "value_id": "v-duplicate-id",
                        "primary_object_id": "object-1",
                        "object_name": "Deployment",
                        "facet": "property",
                        "content": "Deployments require review.",
                        "relevance": 0.95,
                    },
                    {
                        **template,
                        "value_id": "v-unique-aspect",
                        "primary_object_id": "object-2",
                        "object_name": "Canary",
                        "facet": "procedure",
                        "content": "Promote canary after green smoke checks.",
                        "relevance": 0.85,
                        "explanation": {
                            **template["explanation"],
                            "item_facet": "procedure",
                        },
                    },
                ]
            return RetrieveContextResult(
                {
                    "schema_version": 2,
                    "retrieval_request_id": "retrieval-dup-test",
                    "items": items,
                    "memory_injection": {
                        "format": "facet_legend",
                        "text": (
                            "How to read memory:\n"
                            "property — a stable characteristic.\n"
                            "procedure — a repeatable process.\n\n"
                            "M1: [property] Deployment: Deployments require review."
                        ),
                        "legend": [
                            "property — a stable characteristic.",
                            "procedure — a repeatable process.",
                        ],
                        "item_count": len(items),
                    },
                }
            )

    class BatchEmbedder:
        def embed_query_batch_with_metadata(self, memory_space_id, texts):
            assert memory_space_id == "space"
            return [
                ((float(index + 1), 0.0), (0.0, float(index + 1)), "embedder", "2026-08")
                for index, _ in enumerate(texts)
            ]

    class EchoReranker:
        def score(self, query, documents):
            return [1.0 - (index * 0.1) for index, _ in enumerate(documents)]

    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            MultiAspectDuplicateGateway(),
            max_body_bytes=100_000,
            query_embedder=BatchEmbedder(),
            reranker=EchoReranker(),
            reranker_config=SimpleNamespace(
                soft_budget=100_000,
                selection_policy="adaptive_k",
                candidate_policy="semantic",
            ),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={
            "memory_space_id": "space",
            "query": (
                "What is the authorized next dispatcher slice, "
                "its entrypoint and production activation status?"
            ),
            "visible_value_ids": ["v-already-visible"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    ids = [item["value_id"] for item in payload["items"]]
    assert "v-already-visible" not in ids
    assert "v-duplicate-id" not in ids
    assert "v-primary" in ids
    assert "v-unique-aspect" in ids


def test_multi_aspect_preserves_all_32_primary_candidates_and_appends_8_aspects() -> None:
    from types import SimpleNamespace

    full_query = "dispatcher slice, its entrypoint and production activation status"

    class Gateway(_Gateway):
        def retrieve_context(self, request):
            original = super().retrieve_context(request).payload
            template = dict(original["items"][0])
            if request.query_text == full_query:
                ids = [f"primary-{index}" for index in range(1, 33)]
            else:
                suffix = request.request_id.rsplit(":", 1)[-1]
                ids = [f"aspect-{suffix}-{row}" for row in range(1, 9)]
            original["items"] = [
                {
                    **template,
                    "value_id": value_id,
                    "content": f"Fact for {value_id}.",
                    "relevance": 0.9 - idx * 0.01,
                }
                for idx, value_id in enumerate(ids)
            ]
            original["memory_injection"]["item_count"] = len(ids)
            return RetrieveContextResult(original)

    class BatchEmbedder:
        def embed_query_batch_with_metadata(self, memory_space_id, texts):
            return [
                ((float(index), 0.0), (0.0, float(index)), "embedder", "2026-08")
                for index, _ in enumerate(texts)
            ]

    class InspectingReranker:
        def __init__(self) -> None:
            self.seen_counts: list[int] = []

        def score(self, query, documents):
            self.seen_counts.append(len(documents))
            return [
                5.0
                if "primary-29." in doc
                else 4.9
                if "primary-30." in doc
                else 4.8
                if "aspect-0-1." in doc
                else -5.0
                for doc in documents
            ]

    reranker = InspectingReranker()
    app = FastAPI()
    app.include_router(
        create_context_router(
            lambda: "token",
            Gateway(),
            max_body_bytes=100_000,
            query_embedder=BatchEmbedder(),
            reranker=reranker,
            reranker_config=SimpleNamespace(
                soft_budget=100_000,
                selection_policy="adaptive_k",
                candidate_policy="semantic",
            ),
        )
    )
    response = TestClient(app).post(
        "/context/retrieve",
        json={"memory_space_id": "space", "query": full_query},
    )

    assert response.status_code == 200
    payload = response.json()
    diag = payload["selection_diagnostics"]
    assert diag["aspect_query_count"] == 3
    assert diag["aspect_candidate_count"] == 8
    assert diag["candidate_count"] == 40
    assert all(count == 40 for count in reranker.seen_counts)
    assert {row["value_id"] for row in diag["ranking"][:3]} == {
        "primary-29",
        "primary-30",
        "aspect-0-1",
    }
    assert {item["value_id"] for item in payload["items"]} == {
        "primary-29",
        "primary-30",
        "aspect-0-1",
    }
