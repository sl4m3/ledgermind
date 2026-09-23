from __future__ import annotations

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
        return RetrieveContextResult(
            {
                "retrieval_request_id": "retrieval-1",
                "items": [
                    {
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
                ],
                "memory_injection": {
                    "format": "facet_legend",
                    "text": "How to read memory:\nproperty — a stable characteristic.\n\nM1: [property] Deployment: Deployments require review.",
                    "legend": ["property — a stable characteristic."],
                    "item_count": 1,
                },
            }
        )

    def record_retrieval_outcome(
        self, command: RecordRetrievalOutcomeCommand
    ) -> None:
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
    assert gateway.outcomes[0].candidate_value_ids == ("value-1",)
    assert gateway.outcomes[0].delivered_value_ids == ("value-1",)


def test_optional_reranker_uses_core_pool_and_records_only_injected_values() -> None:
    class Gateway(_Gateway):
        def retrieve_context(self, request: RetrieveContextCommand) -> RetrieveContextResult:
            assert request.limit == 32
            original = super().retrieve_context(request).payload
            original["items"] = [
                {**original["items"][0], "value_id": f"value-{index}",
                 "content": f"Rule {index}."} for index in range(1, 9)
            ]
            original["memory_injection"]["item_count"] = 8
            return RetrieveContextResult(original)

    class Reranker:
        def score(self, query: str, documents: list[str]) -> list[float]:
            assert len(documents) == 8
            return [float(index) for index in range(8)]

    gateway = Gateway()
    app = FastAPI()
    app.include_router(create_context_router(
        lambda: "token", gateway, max_body_bytes=100_000,
        query_embedder=_Embedder(), reranker=Reranker(),
    ))
    response = TestClient(app).post(
        "/context/retrieve", json={"memory_space_id": "space", "query": "deployment"}
    )
    assert response.status_code == 200
    assert response.headers["X-LedgerMind-Selection"] == "reranked"
    payload = response.json()
    assert len(payload["items"]) >= 6
    assert payload["items"][0]["value_id"] == "value-8"
    assert payload["delivered_value_ids"] == [item["value_id"] for item in payload["items"]]
    assert payload["selection_diagnostics"]["status"] == "reranked"
    assert payload["selection_diagnostics"]["candidate_count"] == 8
    assert len(gateway.outcomes[0].candidate_value_ids) == 8
    assert gateway.outcomes[0].delivered_value_ids == tuple(payload["delivered_value_ids"])


def test_reranker_failure_uses_core_order() -> None:
    class Broken:
        def score(self, query: str, documents: list[str]) -> list[float]:
            raise RuntimeError("unavailable")

    gateway = _Gateway()
    app = FastAPI()
    app.include_router(create_context_router(
        lambda: "token", gateway, max_body_bytes=100_000,
        query_embedder=_Embedder(), reranker=Broken(),
    ))
    response = TestClient(app).post(
        "/context/retrieve", json={"memory_space_id": "space", "query": "deployment"}
    )
    assert response.status_code == 200
    assert response.headers["X-LedgerMind-Selection"] == "core_fallback"
    assert response.json()["delivered_value_ids"] == ["value-1"]
    assert response.json()["selection_diagnostics"]["fallback_reason"] == "RuntimeError"
