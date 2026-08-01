"""Mapping helpers from transport contracts to domain commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ledgermind_core.contracts.context_v1 import RetrieveContextRequestV1
from ledgermind_core.contracts.atom_v1 import IngestAtomRequestV1
from ledgermind_core.domain import AtomContent, ExtractionInfo, SourceReference


@dataclass(frozen=True, slots=True)
class IngestAtomCommand:
    idempotency_key: str
    request_hash: str
    memory_space_id: str
    source: SourceReference
    content: AtomContent
    extraction: ExtractionInfo


@dataclass(frozen=True, slots=True)
class RetrieveContextQuery:
    memory_space_id: str
    query: str
    limit: int = 5
    min_phase: str | None = None


def _normalize_text(value: str) -> str:
    return value.strip()


def _to_source_reference(raw: IngestAtomRequestV1) -> SourceReference:
    return SourceReference(
        source_system=raw.source.source_system,
        source_instance_id=_normalize_text(raw.source.source_instance_id),
        source_profile_id=_normalize_text(raw.source.source_profile_id),
        source_session_id=_normalize_text(raw.source.source_session_id),
        source_round_id=_normalize_text(raw.source.source_round_id),
        first_message_id=(
            _normalize_text(raw.source.first_message_id)
            if raw.source.first_message_id is not None
            else None
        ),
        final_message_id=(
            _normalize_text(raw.source.final_message_id)
            if raw.source.final_message_id is not None
            else None
        ),
        message_ids=tuple(_normalize_text(message_id) for message_id in raw.source.message_ids),
        source_digest=raw.source.source_digest,
        source_schema_version=raw.source.source_schema_version,
        resolver_version=raw.source.resolver_version,
    )


def _to_atom_content(raw: IngestAtomRequestV1) -> AtomContent:
    return AtomContent(
        title=_normalize_text(raw.atom.title),
        target=_normalize_text(raw.atom.target),
        statement=_normalize_text(raw.atom.statement),
        rationale=_normalize_text(raw.atom.rationale),
        result=_normalize_text(raw.atom.result),
        artifacts=tuple(_normalize_text(artifact) for artifact in raw.atom.artifacts),
    )


def _to_extraction(raw: IngestAtomRequestV1) -> ExtractionInfo:
    return ExtractionInfo(
        host=_normalize_text(raw.extraction.host),
        provider=_normalize_text(raw.extraction.provider),
        model=_normalize_text(raw.extraction.model),
        prompt_version=raw.extraction.prompt_version,
        schema_version=raw.extraction.schema_version,
        purpose=_normalize_text(raw.extraction.purpose),
    )


def map_ingest_atom_request(payload: Mapping[str, object], request_hash: str) -> IngestAtomCommand:
    api_version = payload.get("api_version")
    if api_version != "1":
        raise ValueError("unsupported api_version")

    request = IngestAtomRequestV1.model_validate(payload)

    if request.idempotency_key != request_hash:
        raise ValueError("request checksum mismatch")

    return IngestAtomCommand(
        idempotency_key=request.idempotency_key,
        request_hash=request_hash,
        memory_space_id=_normalize_text(request.memory_space_id),
        source=_to_source_reference(request),
        content=_to_atom_content(request),
        extraction=_to_extraction(request),
    )


def map_context_query(payload: Mapping[str, object]) -> RetrieveContextQuery:
    request = RetrieveContextRequestV1.model_validate(payload)

    return RetrieveContextQuery(
        memory_space_id=_normalize_text(request.memory_space_id),
        query=request.query,
        limit=request.limit,
        min_phase=request.min_phase,
    )


__all__ = [
    "IngestAtomCommand",
    "RetrieveContextQuery",
    "map_ingest_atom_request",
    "map_context_query",
]
