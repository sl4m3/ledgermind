"""Public ContextView endpoint backed directly by the Core gateway."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ledgermind_local.core_gateway import (
    DomainRejectedError,
    RecordRetrievalOutcomeCommand,
    RetrieveContextCommand,
    RetrieveContextResult,
    TransientCoreError,
)
from ledgermind_local.inference.retrieval_reranker import (
    Reranker,
    pack_items,
    rank_items,
)

from .http import build_request_id, error_payload, validate_json_request_headers

logger = logging.getLogger(__name__)


class ContextGateway(Protocol):
    """Core context boundary used by the public retrieval route."""

    def retrieve_context(
        self, request: RetrieveContextCommand
    ) -> RetrieveContextResult: ...

    def record_retrieval_outcome(
        self, command: RecordRetrievalOutcomeCommand
    ) -> None: ...


class QueryEmbedder(Protocol):
    def embed_query(self, memory_space_id: str, query: str) -> Sequence[float]: ...


class ContextRetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    memory_space_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=20_000)
    limit: int = Field(default=5, ge=1, le=50)
    query_embedding: list[float] | None = Field(default=None, min_length=1, max_length=8_192)
    object_query_embedding: list[float] | None = Field(
        default=None, min_length=1, max_length=8_192
    )
    embedding_model_id: str | None = Field(default=None, min_length=1, max_length=200)
    embedding_model_version: str | None = Field(default=None, min_length=1, max_length=200)
    project_id: str | None = Field(default=None, min_length=1, max_length=200)
    repository_id: str | None = Field(default=None, min_length=1, max_length=200)
    task_id: str | None = Field(default=None, min_length=1, max_length=200)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=200)
    query_language: str | None = Field(default=None, min_length=1, max_length=32)
    target_id: str | None = Field(default=None, min_length=1, max_length=200)
    target_alias: str | None = Field(default=None, min_length=1, max_length=200)
    related_object_ids: list[str] | None = None
    requested_facets: list[str] | None = None
    explanation_level: Literal["compact", "none"] = "compact"


class ContextItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value_id: str
    primary_object_id: str
    object_name: str
    target_id: str | None = None
    target_name: str | None = None
    target_breadcrumb: list[str] = Field(default_factory=list, max_length=16)
    facet: str
    content: str
    scope_text: str | None = None
    content_language: str | None = None
    conditions: list[dict[str, str]] = Field(default_factory=list)
    relevance: float = Field(ge=0.0, le=1.0)
    explanation: dict[str, object]


class MemoryInjectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["facet_legend"]
    text: str = Field(max_length=65_536)
    legend: list[str] = Field(default_factory=list, max_length=14)
    item_count: int = Field(ge=0, le=100)


class ContextViewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    items: list[ContextItemResponse]
    retrieval_request_id: str
    delivered_value_ids: list[str] = Field(default_factory=list)
    memory_injection: MemoryInjectionResponse | None = None
    selection_diagnostics: dict[str, object] | None = None


def create_context_router(
    require_token: Callable[..., str],
    context_gateway: ContextGateway | None,
    *,
    max_body_bytes: int,
    query_embedder: QueryEmbedder | None = None,
    reranker: Reranker | None = None,
    reranker_config: object | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/context/retrieve", response_model=ContextViewResponse)
    def retrieve_context(
        payload: ContextRetrieveRequest,
        request: Request,
        response: Response,
        _token: str = Depends(require_token),
    ) -> ContextViewResponse:
        validate_json_request_headers(request.headers, max_bytes=max_body_bytes)
        if context_gateway is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_payload("core_unavailable", "Core gateway is unavailable"),
            )
        request_id = build_request_id(request.headers)
        response.headers["X-Request-ID"] = request_id
        try:
            embedding_model_id = payload.embedding_model_id or "retrieval-embedder"
            embedding_model_version = payload.embedding_model_version or "1"
            query_embedding: list[float]
            object_query_embedding: list[float] | None = None
            if query_embedder is not None:
                embed_with_metadata = getattr(query_embedder, "embed_query_with_metadata", None)
                if callable(embed_with_metadata):
                    embedded, embedding_model_id, embedding_model_version = embed_with_metadata(
                        payload.memory_space_id, payload.query
                    )
                    query_embedding = [float(component) for component in embedded]
                else:
                    query_embedding = [
                        float(component)
                        for component in query_embedder.embed_query(
                            payload.memory_space_id, payload.query
                        )
                    ]
                embed_object_with_metadata = getattr(
                    query_embedder, "embed_object_query_with_metadata", None
                )
                if callable(embed_object_with_metadata):
                    object_embedded, object_model_id, object_model_version = (
                        embed_object_with_metadata(payload.memory_space_id, payload.query)
                    )
                    if (
                        object_model_id != embedding_model_id
                        or object_model_version != embedding_model_version
                    ):
                        raise TransientCoreError(
                            "value and object query embedding identities disagree"
                        )
                    object_query_embedding = [
                        float(component) for component in object_embedded
                    ]
            else:
                if payload.query_embedding is None:
                    raise TransientCoreError("embedding profile is unavailable")
                query_embedding = payload.query_embedding
                object_query_embedding = payload.object_query_embedding
            retrieve = getattr(context_gateway, "retrieve_context", None)
            if not callable(retrieve):
                raise TransientCoreError("Core retrieval is unavailable")
            result = retrieve(
                RetrieveContextCommand(
                    request_id=request_id,
                    memory_space_id=payload.memory_space_id,
                    query_text=payload.query,
                    query_embedding=tuple(query_embedding),
                    object_query_embedding=(
                        tuple(object_query_embedding)
                        if object_query_embedding is not None
                        else None
                    ),
                    embedding_model_id=embedding_model_id,
                    embedding_model_version=embedding_model_version,
                    # The public caller limit remains the old safety cap in
                    # Core-only mode. Reranking requires the Core-admitted pool.
                    limit=32 if reranker is not None else payload.limit,
                    project_id=payload.project_id,
                    repository_id=payload.repository_id,
                    task_id=payload.task_id,
                    conversation_id=payload.conversation_id,
                    query_language=payload.query_language,
                    target_id=payload.target_id,
                    target_alias=payload.target_alias,
                    related_object_ids=tuple(payload.related_object_ids or ()),
                    requested_facets=tuple(payload.requested_facets or ()),
                    explanation_level=payload.explanation_level,
                )
            )
            response_payload = _context_response(result.payload)
            core_items = response_payload["items"]
            candidate_ids = tuple(str(item["value_id"]) for item in core_items)
            if reranker is not None and core_items:
                original = response_payload.get("memory_injection") or {}
                started = time.monotonic()
                fallback_reason: str | None = None
                try:
                    ranked = rank_items(payload.query, core_items, reranker)
                    selection_status = "reranked"
                except (
                    ImportError,
                    OSError,
                    RuntimeError,
                    TimeoutError,
                    TypeError,
                    ValueError,
                ) as exc:
                    logger.warning("local reranker fallback to Core order: %s", type(exc).__name__)
                    ranked = core_items
                    selection_status = "core_fallback"
                    fallback_reason = type(exc).__name__
                try:
                    selected, injection, tokens = pack_items(
                        ranked, original, payload.query_language,
                        min_k=int(getattr(reranker_config, "min_k", 6)),
                        soft_budget=int(getattr(reranker_config, "soft_budget", 400)),
                    )
                    response_payload["items"] = selected
                    response_payload["memory_injection"] = injection
                    response_payload["selection_diagnostics"] = {
                        "status": selection_status,
                        "candidate_count": len(core_items),
                        "injected_count": len(selected),
                        "estimated_injection_tokens": tokens,
                        "latency_ms": round((time.monotonic() - started) * 1000, 2),
                        "fallback_reason": fallback_reason,
                    }
                    response.headers["X-LedgerMind-Selection"] = selection_status
                    logger.info(
                        "retrieval selection status=%s candidates=%d injected=%d tokens=%d",
                        selection_status, len(core_items), len(selected), tokens,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    # A formatting mismatch must not suppress recall. Keep
                    # Core's intact response and make the fallback visible.
                    logger.warning("local injection fallback to Core: %s", type(exc).__name__)
                    response.headers["X-LedgerMind-Selection"] = "core_fallback"
                    response_payload["selection_diagnostics"] = {
                        "status": "core_fallback", "candidate_count": len(core_items),
                        "injected_count": len(core_items),
                        "estimated_injection_tokens": None,
                        "latency_ms": round((time.monotonic() - started) * 1000, 2),
                        "fallback_reason": type(exc).__name__,
                    }
            record_outcome = getattr(
                context_gateway, "record_retrieval_outcome", None
            )
            retrieval_request_id = response_payload["retrieval_request_id"]
            response_items = response_payload["items"]
            delivered_ids = tuple(str(item["value_id"]) for item in response_items)
            if callable(record_outcome) and candidate_ids:
                # Core's candidate set and the injected subset are distinct.
                record_outcome(
                    RecordRetrievalOutcomeCommand(
                        request_id=request_id,
                        retrieval_request_id=retrieval_request_id,
                        candidate_value_ids=candidate_ids,
                        delivered_value_ids=delivered_ids,
                    )
                )
            response_payload["delivered_value_ids"] = list(delivered_ids)
            return ContextViewResponse.model_validate(response_payload)
        except DomainRejectedError as exc:
            logger.warning("context retrieval rejected: %s", exc.code)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_payload(exc.code, exc.detail),
            ) from exc
        except TransientCoreError as exc:
            logger.warning("context retrieval Core unavailable: %s", str(exc)[:240])
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_payload("core_unavailable", str(exc)),
            ) from exc
        except ValueError as exc:
            logger.warning("context retrieval response validation failed: %s", str(exc)[:240])
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_payload("validation_failed", str(exc)),
            ) from exc
        except RuntimeError as exc:
            logger.warning("context retrieval runtime failure: %s", str(exc)[:240])
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_payload("core_unavailable", str(exc)),
            ) from exc
        except Exception as exc:
            logger.exception("context retrieval unexpected failure: %s", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_payload(
                    "context_retrieval_failed", "context retrieval failed"
                ),
            ) from exc

    return router


__all__ = [
    "ContextGateway",
    "ContextItemResponse",
    "ContextRetrieveRequest",
    "ContextViewResponse",
    "MemoryInjectionResponse",
    "QueryEmbedder",
    "create_context_router",
]


def _context_response(payload: dict[str, object]) -> dict[str, Any]:
    try:
        from ledgermind_protocol.object_facet import RetrievalResponse

        response = RetrievalResponse.model_validate(_normalize_legacy_context_payload(payload))
    except (ImportError, TypeError, ValueError) as exc:
        raise ValueError("Core retrieval response is not a strict object-facet response") from exc
    items = []
    for item in response.items:
        rendered = item.model_dump(mode="json")
        # ContextView intentionally exposes the value-level explanation but
        # keeps source event ids in Core-owned provenance storage.
        rendered.pop("source_event_ids", None)
        items.append(rendered)
    return {
        "schema_version": 2,
        "retrieval_request_id": response.retrieval_request_id,
        "items": items,
        "memory_injection": (
            response.memory_injection.model_dump(mode="json")
            if response.memory_injection is not None
            else None
        ),
    }


def _normalize_legacy_context_payload(payload: dict[str, object]) -> dict[str, object]:
    """Keep the HTTP boundary compatible with older test/core adapters.

    Production Core responses already contain the full truthful score
    components. Older in-process adapters used a compact component map; it
    is expanded here only at the compatibility boundary and never written
    back to Core.
    """

    normalized = dict(payload)
    items = []
    for raw_item in payload.get("items", []):
        if not isinstance(raw_item, dict):
            items.append(raw_item)
            continue
        item = dict(raw_item)
        # ``source_kind`` is Core-owned provenance used by the durable audit
        # and retrieval internals.  It is intentionally not part of the
        # public ContextView contract, so remove it before validating the
        # strict RetrievalResponse boundary instead of letting a newer Core
        # response turn an otherwise valid retrieval into HTTP 503.
        item.pop("source_kind", None)
        # Old in-process adapters did not expose provenance. Keep that
        # adapter usable with an explicit compatibility marker; real Core
        # responses always carry source-owned event ids.
        if not item.get("source_event_ids"):
            item["source_event_ids"] = ["legacy:compat"]
        explanation = item.get("explanation")
        if isinstance(explanation, dict):
            explanation = dict(explanation)
            components = explanation.get("score_components")
            if isinstance(components, dict) and "semantic" in components:
                compact = components
                semantic = float(compact.get("semantic", 0.0))
                object_score = float(compact.get("object", 0.0))
                facet = float(compact.get("facet", 0.0))
                scope_time = float(compact.get("scope_time", 0.0))
                context = float(compact.get("context", 0.0))
                recency = float(compact.get("recency", 0.0))
                support = float(compact.get("support", 0.0))
                usage = float(compact.get("usage", 0.0))
                explanation["score_components"] = {
                    "semantic_similarity": semantic,
                    "semantic_similarity_raw": semantic,
                    "semantic_contribution": semantic,
                    "object_similarity": object_score,
                    "object_similarity_raw": object_score,
                    "object_card_cosine": object_score,
                    "lexical_object_match": object_score,
                    "object_contribution": object_score,
                    "facet_compatibility": facet,
                    "facet_contribution": facet,
                    "scope_time_compatibility": scope_time,
                    "scope_time_contribution": scope_time,
                    "context_compatibility": context,
                    "context_contribution": context,
                    "recency_component": recency,
                    "recency_contribution": recency,
                    "support_component": support,
                    "support_contribution": support,
                    "usage_component": usage,
                    "usage_contribution": usage,
                    "final_score": float(item.get("relevance", 0.0)),
                }
            item["explanation"] = explanation
        items.append(item)
    normalized["items"] = items
    return normalized
