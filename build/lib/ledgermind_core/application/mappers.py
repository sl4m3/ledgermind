"""Mapping helpers from transport contracts to domain commands."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ledgermind_core.contracts.atom import IngestAtomRequest
from ledgermind_core.contracts.context import RetrieveContextRequest
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


@dataclass(frozen=True, slots=True)
class SupersedeKnowledgeCommand:
    memory_space_id: str
    old_knowledge_ids: tuple[str, ...]
    replacement_title: str
    replacement_target: str
    replacement_statement: str
    replacement_rationale: str
    cause_atom_id: str | None
    expected_versions: dict[str, int]

    def __post_init__(self) -> None:
        if not self.memory_space_id:
            raise ValueError("memory_space_id must not be empty")
        if not self.old_knowledge_ids:
            raise ValueError("old_knowledge_ids must not be empty")
        if len(set(self.old_knowledge_ids)) != len(self.old_knowledge_ids):
            raise ValueError("old_knowledge_ids must not contain duplicates")

        if set(self.expected_versions.keys()) != set(self.old_knowledge_ids):
            raise ValueError("expected_versions must include every old_knowledge_id")

        if not self.replacement_title.strip():
            raise ValueError("replacement_title must not be empty")
        if not self.replacement_target.strip():
            raise ValueError("replacement_target must not be empty")
        if not self.replacement_statement.strip():
            raise ValueError("replacement_statement must not be empty")
        if not self.replacement_rationale.strip():
            raise ValueError("replacement_rationale must not be empty")


def _normalize_text(value: str) -> str:
    return value.strip()


def _to_source_reference(raw: IngestAtomRequest) -> SourceReference:
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


def _to_atom_content(raw: IngestAtomRequest) -> AtomContent:
    return AtomContent(
        title=_normalize_text(raw.atom.title),
        target=_normalize_text(raw.atom.target),
        statement=_normalize_text(raw.atom.statement),
        rationale=_normalize_text(raw.atom.rationale),
        result=_normalize_text(raw.atom.result),
        artifacts=tuple(_normalize_text(artifact) for artifact in raw.atom.artifacts),
    )


def _to_extraction(raw: IngestAtomRequest) -> ExtractionInfo:
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

    request = IngestAtomRequest.model_validate(payload)

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
    request = RetrieveContextRequest.model_validate(payload)

    return RetrieveContextQuery(
        memory_space_id=_normalize_text(request.memory_space_id),
        query=request.query,
        limit=request.limit,
        min_phase=request.min_phase,
    )


__all__ = [
    "IngestAtomCommand",
    "RetrieveContextQuery",
    "SupersedeKnowledgeCommand",
    "map_context_query",
    "map_ingest_atom_request",
]
