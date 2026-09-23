"""Strict object-facet and claim-first retrieval contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, TypeAlias, cast

from pydantic import Field, StrictBool, StrictInt, model_validator

from .models import LedgerMindResolution, ProtocolModel

MAX_MENTIONS = 24
MAX_MENTION_CANDIDATES = 8
MAX_IDENTIFIER_LENGTH = 500
MAX_ALIASES = 32
MAX_MATCH_REASONS = 16
MAX_SOURCE_EVENT_IDS = 1_000
MAX_CONTENT_LENGTH = 20_000
MAX_SCOPE_TEXT_LENGTH = 20_000
MAX_RELATED_REFS = 32
MAX_RESULT_OBJECTS = 128
MAX_RESULT_VALUES = 512
MAX_CLAIMS = 128
MAX_CLAIM_CONDITIONS = 32
MAX_CLAIM_CONTEXT_ANCHORS = 32
MAX_CLAIM_REFS = 32
MAX_COVERAGE_ENTRIES = 128
MAX_RETRIEVAL_ITEMS = 100
MAX_EXPLANATION_REASONS = 32
MAX_EXPLANATION_SIGNALS = 32
MAX_REQUESTED_FACETS = 14
MAX_CONTEXT_IDS = 100
MAX_TASK_MESSAGES = 256
MAX_OUTPUT_TOKENS = 262_144
MAX_EMBEDDING_TEXTS = 512
MAX_EMBEDDING_DIMENSIONS = 8_192
MAX_EMBEDDING_VECTORS = 512
MAX_EMBEDDING_ABSOLUTE_VALUE = 1_000_000.0
MAX_EMBEDDING_TEXT_LENGTH = 2_000
MAX_RETRIEVAL_OUTCOME_IDS = 100
MAX_U64 = 18_446_744_073_709_551_615

Facet: TypeAlias = Literal[
    "identity",
    "property",
    "state",
    "function",
    "structure",
    "procedure",
    "maintenance",
    "risk",
    "constraint",
    "preference",
    "decision",
    "experience",
    "relation",
    "event",
]
ObjectResolution: TypeAlias = Literal["existing", "new", "ambiguous"]
CoverageDisposition: TypeAlias = Literal[
    "claim",
    "duplicate",
    "ephemeral",
    "insufficient_evidence",
]
ObjectReason: TypeAlias = Literal[
    "technical_identifier_exact",
    "canonical_exact",
    "lexical_similarity",
    "object_card_embedding",
    "project_match",
    "repository_match",
    "task_match",
    "related_object_match",
    "conversation_match",
    "direct_value_semantic",
]
IngestStatus: TypeAlias = Literal["queued", "processing", "completed", "failed"]
TaskKind: TypeAlias = Literal["generate_json", "embed_texts"]
ProfileSlot: TypeAlias = Literal["operational", "background", "embedding"]
EmbeddingPurpose: TypeAlias = Literal[
    "object_query",
    "subject_query",
    "object_mention",
    "object_card",
    "target_card",
    "value_record",
    "retrieval_query",
    "facet_catalog",
]
ResponseFormat: TypeAlias = Literal["json_object", "text"]
StructuredOutputMode: TypeAlias = Literal[
    "auto", "json_schema", "tool_call", "json_object", "prompt_only"
]
ExplanationLevel: TypeAlias = Literal["compact", "none"]

FACET_VALUES = frozenset(
    {
        "identity",
        "property",
        "state",
        "function",
        "structure",
        "procedure",
        "maintenance",
        "risk",
        "constraint",
        "preference",
        "decision",
        "experience",
        "relation",
        "event",
    }
)
OBJECT_REASON_VALUES = frozenset(
    {
        "technical_identifier_exact",
        "canonical_exact",
        "lexical_similarity",
        "object_card_embedding",
        "project_match",
        "repository_match",
        "task_match",
        "related_object_match",
        "conversation_match",
        "direct_value_semantic",
    }
)


def _require_identifier(value: str, name: str) -> None:
    if not value or not value.strip() or len(value) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(
            f"{name} must be a non-empty string of at most {MAX_IDENTIFIER_LENGTH} characters"
        )


def _require_text(value: str, name: str, maximum: int) -> None:
    if not value or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a non-empty string of at most {maximum} characters")


def _validate_unique(values: Sequence[object], name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _validate_ids(values: list[str], name: str, maximum: int, *, minimum: int = 1) -> None:
    if not minimum <= len(values) <= maximum:
        raise ValueError(f"{name} must contain between {minimum} and {maximum} entries")
    for value in values:
        _require_identifier(value, name.rstrip("s"))
    _validate_unique(values, name)


def _validate_claim_span(
    span_start: int,
    span_end: int,
    surface_text: str,
    name: str,
) -> None:
    if span_end <= span_start:
        raise ValueError(f"{name} span must have a positive length")
    expected_length = len(surface_text.encode("utf-8"))
    if span_end - span_start != expected_length:
        raise ValueError(f"{name} span length must match surface_text")


def _validate_source_span(
    source: str,
    span_start: int,
    span_end: int,
    surface_text: str,
    name: str,
) -> int:
    _validate_claim_span(span_start, span_end, surface_text, name)
    encoded = source.encode("utf-8")
    if span_end > len(encoded):
        raise ValueError(f"{name} span exceeds the source event")
    try:
        # Decoding both prefixes rejects offsets inside a UTF-8 code point.
        encoded[:span_start].decode("utf-8")
        encoded[:span_end].decode("utf-8")
        selected = encoded[span_start:span_end].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{name} span must use UTF-8 character boundaries") from error
    if selected != surface_text:
        raise ValueError(f"{name} surface_text and span must exactly match the source event")
    return span_start


def _looks_like_uuid(value: str) -> bool:
    parts = value.split("-")
    return len(parts) == 5 and all(
        len(part) == expected and all(character in "0123456789abcdef" for character in part)
        for part, expected in zip(parts, (8, 4, 4, 4, 12))
    )


def _opaque_identifier(value: str) -> bool:
    trimmed = value.strip().strip("\"'`,;.)]}")
    lower = trimmed.lower()
    prefixes = (
        "call-",
        "call_",
        "request-",
        "request_",
        "trace-",
        "trace_",
        "run-",
        "run_",
        "raw_round_id",
        "raw-round-id",
        "retrieval_request_id",
        "retrieval-request-id",
        "idempotency_key",
        "idempotency-key",
    )
    return (
        any(lower.startswith(prefix) and len(lower) > len(prefix) for prefix in prefixes)
        or lower.startswith("sha256:")
        or _looks_like_uuid(lower)
    )


def _validate_source_events(source_events: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(source_events, Mapping):
        raise TypeError("source events must be a mapping")
    validated: dict[str, str] = {}
    for event_id, text in source_events.items():
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("source events must map non-empty IDs to text")
        if not isinstance(text, str):
            raise TypeError("source events must map IDs to text")
        validated[event_id] = text
    return validated


def _condition_occurrences(source: str, surface_text: str) -> list[tuple[int, int]]:
    occurrences: list[tuple[int, int]] = []
    character_offset = 0
    while True:
        found = source.find(surface_text, character_offset)
        if found < 0:
            return occurrences
        byte_start = len(source[:found].encode("utf-8"))
        byte_end = byte_start + len(surface_text.encode("utf-8"))
        occurrences.append((byte_start, byte_end))
        character_offset = found + len(surface_text)


def _require_sha256_digest(value: str, name: str) -> None:
    if len(value) != 71 or not value.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in value[7:]
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")


def _validate_validity_window(valid_from: str | None, valid_to: str | None) -> None:
    parsed_from: datetime | None = None
    parsed_to: datetime | None = None
    if valid_from is not None:
        parsed_from = _parse_rfc3339(valid_from, "valid_from")
    if valid_to is not None:
        parsed_to = _parse_rfc3339(valid_to, "valid_to")
    if parsed_from is not None and parsed_to is not None and parsed_to < parsed_from:
        raise ValueError("valid_to must not precede valid_from")


def _parse_rfc3339(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be RFC3339") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


def _normalize_for_comparison(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(
        str.maketrans(
            cast(
                dict[str, str | int | None],
                {
                    "\u2010": "-",
                    "\u2011": "-",
                    "\u2012": "-",
                    "\u2013": "-",
                    "\u2014": "-",
                    "\u2015": "-",
                    "\u2043": "-",
                    "\u2212": "-",
                    "\ufe58": "-",
                    "\ufe63": "-",
                    "\uff0d": "-",
                    "\u2018": "'",
                    "\u2019": "'",
                    "\u201a": "'",
                    "\u201b": "'",
                    "\u201c": '"',
                    "\u201d": '"',
                    "\u201e": '"',
                    "\u201f": '"',
                },
            )
        )
    )
    normalized = " ".join(normalized.casefold().split())
    return re.sub(r"\s*-\s*", "-", normalized)


def _normalized_contains(text: str, needle: str) -> bool:
    normalized_needle = _normalize_for_comparison(needle)
    return bool(normalized_needle) and normalized_needle in _normalize_for_comparison(text)


def _component_count(value: str) -> int:
    return len(_normalize_for_comparison(value).split())


class ModelRequest(ProtocolModel):
    """Opaque generate-json request prepared by Core."""

    messages: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_TASK_MESSAGES)
    max_output_tokens: int = Field(ge=1, le=MAX_OUTPUT_TOKENS)
    response_format: ResponseFormat | dict[str, Any] | None = None
    output_contract: dict[str, Any] | None = None
    mode: StructuredOutputMode | None = None
    structured_output_mode: StructuredOutputMode | None = None
    tool_name: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict[str, Any] | None = None
    seed: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_messages(self) -> ModelRequest:
        for message in self.messages:
            if not isinstance(message, dict):
                raise TypeError("model messages must be objects")
        return self


class EmbeddingRequest(ProtocolModel):
    """Opaque embedding request prepared by Core."""

    texts: list[str] = Field(min_length=1, max_length=MAX_EMBEDDING_TEXTS)
    purpose: EmbeddingPurpose
    subject_refs: list[str] | None = Field(default=None, max_length=MAX_EMBEDDING_TEXTS)
    dimensions: int | None = Field(default=None, ge=1, le=MAX_EMBEDDING_DIMENSIONS)

    @model_validator(mode="after")
    def validate_texts(self) -> EmbeddingRequest:
        for text in self.texts:
            if not text.strip() or len(text) > MAX_EMBEDDING_TEXT_LENGTH:
                raise ValueError(
                    "embedding text must be a non-empty string of at most "
                    f"{MAX_EMBEDDING_TEXT_LENGTH} characters"
                )
        if self.subject_refs is not None:
            _validate_ids(self.subject_refs, "subject_refs", MAX_EMBEDDING_TEXTS, minimum=0)
        return self


class GenericExecutionTask(ProtocolModel):
    """Technical task; operation and operation_input remain Core-owned."""

    schema_version: Literal[2] = 2
    task_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    task_kind: TaskKind
    operation: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    profile_slot: ProfileSlot
    memory_space_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    expires_at: str
    lease: str | None = None
    model_request: ModelRequest | None = None
    embedding_request: EmbeddingRequest | None = None
    operation_input: dict[str, Any] | None = None
    structured_generation: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_task(self) -> GenericExecutionTask:
        _parse_rfc3339(self.expires_at, "expires_at")
        if self.lease is not None:
            _parse_rfc3339(self.lease, "lease")
        if self.task_kind == "generate_json":
            if self.profile_slot not in {"operational", "background"}:
                raise ValueError(
                    "generate_json task requires an operational or background profile slot"
                )
            if self.model_request is None:
                raise ValueError("generate_json task requires model_request")
            if self.embedding_request is not None:
                raise ValueError("generate_json task forbids embedding_request")
        else:
            if self.profile_slot != "embedding":
                raise ValueError("embed_texts task requires the embedding profile slot")
            if self.embedding_request is None:
                raise ValueError("embed_texts task requires embedding_request")
            if self.model_request is not None:
                raise ValueError("embed_texts task forbids model_request")
        if self.operation_input is not None and not isinstance(self.operation_input, dict):
            raise TypeError("operation_input must be an object")
        return self


class ResolutionContext(ProtocolModel):
    project_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    repository_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    task_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    conversation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )
    related_object_ids: list[str] | None = None

    @model_validator(mode="after")
    def validate_context(self) -> ResolutionContext:
        for value, name in (
            (self.project_id, "project id"),
            (self.repository_id, "repository id"),
            (self.task_id, "task id"),
            (self.conversation_id, "conversation id"),
        ):
            if value is not None:
                _require_identifier(value, name)
        if self.repository_id is not None and self.project_id is None:
            raise ValueError("repository id requires a matching project id")
        if self.related_object_ids is not None:
            _validate_ids(
                self.related_object_ids,
                "related_object_ids",
                MAX_RELATED_REFS,
                minimum=0,
            )
        return self


class IngestRawRoundRequest(ProtocolModel):
    """Core command wrapper for an already validated RawRound payload."""

    schema_version: Literal[2] = 2
    command_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    idempotency_key: str
    memory_space_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    raw_round: dict[str, Any]
    resolution_context: ResolutionContext | None = None
    embedding_profile: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_request(self) -> IngestRawRoundRequest:
        _require_sha256_digest(self.idempotency_key, "idempotency key")
        return self


class IngestRawRoundResponse(ProtocolModel):
    schema_version: Literal[2] = 2
    raw_round_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    duplicate: bool
    operational_job_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    status: IngestStatus


class ObjectCandidate(ProtocolModel):
    object_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    canonical_name: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    aliases: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)
    match_reasons: list[str] = Field(default_factory=list, max_length=MAX_MATCH_REASONS)
    rank: StrictInt = Field(ge=1)
    lexical_score: float = Field(ge=0.0, le=1.0)
    embedding_score: float = Field(ge=0.0, le=1.0)
    context_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    project_match: StrictBool
    repository_match: StrictBool
    task_match: StrictBool
    related_object_match: StrictBool
    conversation_match: StrictBool
    explicit_scope_mismatch: StrictBool

    @model_validator(mode="after")
    def validate_candidate(self) -> ObjectCandidate:
        _require_identifier(self.object_id, "candidate object id")
        _require_text(self.canonical_name, "candidate canonical name", MAX_IDENTIFIER_LENGTH)
        for alias in self.aliases:
            _require_text(alias, "alias", MAX_IDENTIFIER_LENGTH)
        _validate_unique(self.aliases, "aliases")
        for reason in self.match_reasons:
            _require_text(reason, "match reason", MAX_IDENTIFIER_LENGTH)
        return self


class MentionResolutionInput(ProtocolModel):
    mention_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    surface_text: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    normalized_text: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    source_event_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    span_start: StrictInt = Field(ge=0, le=MAX_U64)
    span_end: StrictInt = Field(ge=0, le=MAX_U64)
    candidate_set_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidates: list[ObjectCandidate] = Field(max_length=MAX_MENTION_CANDIDATES)

    @model_validator(mode="after")
    def validate_mention(self) -> MentionResolutionInput:
        _require_identifier(self.mention_ref, "mention ref")
        _require_identifier(self.source_event_id, "source event id")
        if _normalize_for_comparison(self.surface_text) != self.normalized_text:
            raise ValueError("normalized_text does not match the name normalizer")
        if self.span_end <= self.span_start:
            raise ValueError("mention span must have a positive length")
        if self.span_end > len(self.surface_text):
            raise ValueError("mention span must be within surface_text")
        object_ids = [candidate.object_id for candidate in self.candidates]
        ranks = [candidate.rank for candidate in self.candidates]
        _validate_unique(object_ids, "candidate object ids")
        _validate_unique(ranks, "candidate ranks")
        return self


class OperationalExtractionInput(ProtocolModel):
    schema_version: Literal[2] = 2
    raw_round_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    normalizer_version: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    facet_catalogue_version: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    normalized_round: dict[str, Any]
    mentions: list[MentionResolutionInput] = Field(
        min_length=1,
        max_length=MAX_MENTIONS,
    )
    resolution_context: ResolutionContext

    @model_validator(mode="after")
    def validate_input(self) -> OperationalExtractionInput:
        for value, name in (
            (self.raw_round_id, "raw round id"),
            (self.normalizer_version, "normalizer version"),
            (self.facet_catalogue_version, "facet catalogue version"),
        ):
            _require_identifier(value, name)
        mention_refs = [mention.mention_ref for mention in self.mentions]
        _validate_unique(mention_refs, "mention refs")
        return self


class ClaimSubject(ProtocolModel):
    """Exact source grounding for a claim subject.

    Span offsets are UTF-8 byte offsets, matching Core's source-event contract.
    """

    source_event_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    surface_text: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    span_start: StrictInt = Field(ge=0, le=MAX_U64)
    span_end: StrictInt = Field(ge=0, le=MAX_U64)

    @model_validator(mode="after")
    def validate_subject(self) -> ClaimSubject:
        self._validate_subject_fields()
        return self

    def _validate_subject_fields(self) -> None:
        _require_identifier(self.source_event_id, "subject source event id")
        _require_text(self.surface_text, "subject surface text", MAX_CONTENT_LENGTH)
        _validate_claim_span(self.span_start, self.span_end, self.surface_text, "subject")


class ClaimCondition(ProtocolModel):
    """Exact source evidence for a claim condition."""

    source_event_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    surface_text: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)

    @model_validator(mode="after")
    def validate_condition(self) -> ClaimCondition:
        self._validate_condition_fields()
        return self

    def _validate_condition_fields(self) -> None:
        _require_identifier(self.source_event_id, "condition source event id")
        _require_text(self.surface_text, "condition surface text", MAX_CONTENT_LENGTH)


class ExtractedClaim(ProtocolModel):
    """Provider-extracted claim before Core derives a resolved subject."""

    claim_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    subject: ClaimSubject
    facet: Facet
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    conditions: list[ClaimCondition] = Field(
        default_factory=list,
        max_length=MAX_CLAIM_CONDITIONS,
    )
    context_anchor_refs: list[str] = Field(
        default_factory=list,
        max_length=MAX_CLAIM_CONTEXT_ANCHORS,
    )
    source_event_ids: list[str] = Field(
        min_length=1,
        max_length=MAX_SOURCE_EVENT_IDS,
    )

    @model_validator(mode="after")
    def validate_claim(self) -> ExtractedClaim:
        self._validate_claim_fields()
        return self

    def _validate_claim_fields(self) -> None:
        _require_identifier(self.claim_ref, "claim ref")
        self.subject._validate_subject_fields()
        if _opaque_identifier(self.subject.surface_text):
            raise ValueError("subject must not be an opaque identifier")
        _require_text(self.content, "content", MAX_CONTENT_LENGTH)
        for condition in self.conditions:
            condition._validate_condition_fields()
        condition_keys = [
            (condition.source_event_id, condition.surface_text)
            for condition in self.conditions
        ]
        _validate_unique(condition_keys, "conditions")
        for anchor_ref in self.context_anchor_refs:
            _require_identifier(anchor_ref, "context anchor ref")
        _validate_unique(self.context_anchor_refs, "context_anchor_refs")
        _validate_ids(self.source_event_ids, "source_event_ids", MAX_SOURCE_EVENT_IDS)
        if self.subject.source_event_id not in self.source_event_ids:
            raise ValueError("source_event_ids must include the subject source event")
        for condition in self.conditions:
            if condition.source_event_id not in self.source_event_ids:
                raise ValueError(
                    "source_event_ids must include every condition source event"
                )

    def validate_with_source(self, source_events: Mapping[str, str]) -> None:
        self._validate_claim_fields()
        events = _validate_source_events(source_events)
        subject_source = events.get(self.subject.source_event_id)
        if subject_source is None:
            raise ValueError(
                f"unknown subject source event {self.subject.source_event_id}"
            )
        subject_start = _validate_source_span(
            subject_source,
            self.subject.span_start,
            self.subject.span_end,
            self.subject.surface_text,
            "subject",
        )
        for event_id in self.source_event_ids:
            if event_id not in events:
                raise ValueError(f"unknown source event {event_id}")
        for condition in self.conditions:
            condition_source = events.get(condition.source_event_id)
            if condition_source is None:
                raise ValueError(
                    f"unknown condition source event {condition.source_event_id}"
                )
            occurrences = _condition_occurrences(condition_source, condition.surface_text)
            if not occurrences:
                raise ValueError(
                    "condition surface_text is not an exact source substring: "
                    f"{condition.source_event_id}"
                )
            if condition.source_event_id == self.subject.source_event_id and any(
                start <= subject_start and self.subject.span_end <= end
                for start, end in occurrences
            ):
                raise ValueError("subject span must not be contained in a condition span")


class ClaimCoverage(ProtocolModel):
    """Explicit disposition for one requirement/evidence anchor."""

    anchor_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    disposition: CoverageDisposition
    claim_refs: list[str] = Field(default_factory=list, max_length=MAX_CLAIM_REFS)

    @model_validator(mode="after")
    def validate_coverage(self) -> ClaimCoverage:
        self._validate_coverage_fields()
        return self

    def _validate_coverage_fields(self) -> None:
        _require_identifier(self.anchor_ref, "anchor ref")
        for claim_ref in self.claim_refs:
            _require_identifier(claim_ref, "coverage claim ref")
        _validate_unique(self.claim_refs, "coverage claim_refs")
        if self.disposition in {"claim", "duplicate"} and not self.claim_refs:
            raise ValueError("claim and duplicate coverage require at least one claim_ref")
        if self.disposition in {"ephemeral", "insufficient_evidence"} and self.claim_refs:
            raise ValueError(
                "ephemeral and insufficient_evidence coverage forbid claim_refs"
            )


class ClaimExtractionOutput(ProtocolModel):
    """Claim-first operational extraction output owned by Core."""

    schema_version: Literal[1] = 1
    claims: list[ExtractedClaim] = Field(default_factory=list, max_length=MAX_CLAIMS)
    coverage: list[ClaimCoverage] = Field(
        default_factory=list,
        max_length=MAX_COVERAGE_ENTRIES,
    )

    @model_validator(mode="after")
    def validate_output(self) -> ClaimExtractionOutput:
        self._validate_output_fields()
        return self

    def _validate_output_fields(self) -> None:
        for claim in self.claims:
            claim._validate_claim_fields()
        for coverage in self.coverage:
            coverage._validate_coverage_fields()
        claim_refs = [claim.claim_ref for claim in self.claims]
        _validate_unique(claim_refs, "claim refs")
        coverage_anchor_refs = [coverage.anchor_ref for coverage in self.coverage]
        _validate_unique(coverage_anchor_refs, "coverage anchor refs")
        known_claim_refs = set(claim_refs)
        for coverage in self.coverage:
            for claim_ref in coverage.claim_refs:
                if claim_ref not in known_claim_refs:
                    raise ValueError(f"coverage references unknown claim_ref {claim_ref}")

    def validate_with_source(self, source_events: Mapping[str, str]) -> None:
        self._validate_output_fields()
        for claim in self.claims:
            claim.validate_with_source(source_events)

    def validate_coverage_against(self, requirement_anchor_refs: list[str]) -> None:
        self._validate_output_fields()
        if len(requirement_anchor_refs) > MAX_COVERAGE_ENTRIES:
            raise ValueError(
                f"requirement anchor refs must not exceed {MAX_COVERAGE_ENTRIES} entries"
            )
        _validate_unique(requirement_anchor_refs, "requirement anchor refs")
        for anchor_ref in requirement_anchor_refs:
            _require_identifier(anchor_ref, "requirement anchor ref")
        offered = set(requirement_anchor_refs)
        returned = {coverage.anchor_ref for coverage in self.coverage}
        if offered != returned:
            raise ValueError("coverage must contain exactly the offered requirement anchors")


# Names used by the claim-first Core contract and application contour.
SubjectGrounding = ClaimSubject
ConditionGrounding = ClaimCondition
OperationalModelClaim = ExtractedClaim
OperationalModelCoverage = ClaimCoverage
OperationalClaimOutput = ClaimExtractionOutput
OperationalModelClaimOutput = ClaimExtractionOutput


class ResolvedObject(ProtocolModel):
    ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    mention_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    resolution: ObjectResolution
    existing_object_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )
    new_canonical_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )
    ambiguous_candidate_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_MENTION_CANDIDATES,
    )
    aliases_from_source: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)
    source_event_ids: list[str] = Field(min_length=1, max_length=MAX_SOURCE_EVENT_IDS)
    canonical_name_source_event_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )

    @model_validator(mode="after")
    def validate_resolution(self) -> ResolvedObject:
        _require_identifier(self.ref, "object ref")
        _require_identifier(self.mention_ref, "mention ref")
        for alias in self.aliases_from_source:
            _require_text(alias, "source alias", MAX_IDENTIFIER_LENGTH)
        _validate_unique(self.aliases_from_source, "aliases_from_source")
        _validate_ids(self.source_event_ids, "source_event_ids", MAX_SOURCE_EVENT_IDS)
        if self.canonical_name_source_event_id is not None:
            _require_identifier(
                self.canonical_name_source_event_id,
                "canonical name source event id",
            )

        if self.resolution == "existing":
            if self.existing_object_id is None:
                raise ValueError("existing resolution requires existing_object_id")
            if self.new_canonical_name is not None or self.ambiguous_candidate_ids:
                raise ValueError("existing resolution contains new-object fields")
            if self.canonical_name_source_event_id is not None:
                raise ValueError("existing resolution forbids canonical name source evidence")
        elif self.resolution == "new":
            if self.new_canonical_name is None:
                raise ValueError("new resolution requires new_canonical_name")
            if self.existing_object_id is not None or self.ambiguous_candidate_ids:
                raise ValueError("new resolution contains existing or ambiguous fields")
        else:
            if self.new_canonical_name is None:
                raise ValueError("ambiguous resolution requires new_canonical_name")
            if self.existing_object_id is not None:
                raise ValueError("ambiguous resolution forbids existing_object_id")
            if not 2 <= len(self.ambiguous_candidate_ids) <= MAX_MENTION_CANDIDATES:
                raise ValueError("ambiguous resolution requires between 2 and 8 candidates")
            for candidate_id in self.ambiguous_candidate_ids:
                _require_identifier(candidate_id, "ambiguous candidate id")
            _validate_unique(self.ambiguous_candidate_ids, "ambiguous_candidate_ids")
        return self


class ExtractedValue(ProtocolModel):
    primary_object_ref: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    related_object_refs: list[str] = Field(default_factory=list, max_length=MAX_RELATED_REFS)
    facet: Facet
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    content_language: str | None = Field(default=None, min_length=1, max_length=32)
    conditions: list[ClaimCondition] = Field(
        default_factory=list,
        max_length=MAX_CLAIM_CONDITIONS,
    )
    source_event_ids: list[str] = Field(min_length=1, max_length=MAX_SOURCE_EVENT_IDS)
    scope_text: str | None = Field(default=None, min_length=1, max_length=MAX_SCOPE_TEXT_LENGTH)
    valid_from: str | None = None
    valid_to: str | None = None

    @model_validator(mode="after")
    def validate_value(self) -> ExtractedValue:
        _require_identifier(self.primary_object_ref, "primary object ref")
        for object_ref in self.related_object_refs:
            _require_identifier(object_ref, "related object ref")
        _validate_unique(self.related_object_refs, "related_object_refs")
        if self.content_language is not None:
            _require_text(self.content_language, "content language", 32)
        for condition in self.conditions:
            condition._validate_condition_fields()
        _validate_unique(
            [(condition.source_event_id, condition.surface_text) for condition in self.conditions],
            "conditions",
        )
        _validate_ids(self.source_event_ids, "source_event_ids", MAX_SOURCE_EVENT_IDS)
        _validate_validity_window(self.valid_from, self.valid_to)
        return self


class OperationalExtractionResult(ProtocolModel):
    schema_version: Literal[2] = 2
    objects: list[ResolvedObject] = Field(max_length=MAX_RESULT_OBJECTS)
    values: list[ExtractedValue] = Field(max_length=MAX_RESULT_VALUES)

    @model_validator(mode="after")
    def validate_result(self) -> OperationalExtractionResult:
        object_refs = [object_.ref for object_ in self.objects]
        _validate_unique(object_refs, "object refs")
        for value in self.values:
            if value.primary_object_ref not in object_refs:
                raise ValueError(f"unknown object ref {value.primary_object_ref}")
            for object_ref in value.related_object_refs:
                if object_ref not in object_refs:
                    raise ValueError(f"unknown object ref {object_ref}")
        return self

    def validate_with_source(
        self,
        inputs: OperationalExtractionInput,
        source_events: Mapping[str, str],
    ) -> None:
        inputs.model_validate(inputs)
        known_events = set(source_events)
        for event_id, text in source_events.items():
            if not isinstance(event_id, str) or not event_id.strip() or not isinstance(text, str):
                raise ValueError("source events must map non-empty IDs to text")
        for mention in inputs.mentions:
            if mention.source_event_id not in known_events:
                raise ValueError(f"unknown source event {mention.source_event_id}")

        mentions_by_ref = {mention.mention_ref: mention for mention in inputs.mentions}
        for object_ in self.objects:
            selected_mention = mentions_by_ref.get(object_.mention_ref)
            if selected_mention is None:
                raise ValueError(f"unknown mention ref {object_.mention_ref}")
            candidates = {
                candidate.object_id: candidate for candidate in selected_mention.candidates
            }
            for event_id in object_.source_event_ids:
                if event_id not in known_events:
                    raise ValueError(f"unknown source event {event_id}")
            if selected_mention.source_event_id not in object_.source_event_ids:
                raise ValueError("object source_event_ids must include the mention source event")

            if object_.resolution == "existing":
                assert object_.existing_object_id is not None
                candidate = candidates.get(object_.existing_object_id)
                if candidate is None:
                    raise ValueError(
                        f"existing_object_id {object_.existing_object_id} is not among "
                        "the mention candidates"
                    )
                if candidate.explicit_scope_mismatch:
                    raise ValueError(
                        "existing resolution cannot select a scope-mismatched candidate"
                    )
            elif object_.resolution == "ambiguous":
                for candidate_id in object_.ambiguous_candidate_ids:
                    if candidate_id not in candidates:
                        raise ValueError(f"ambiguous candidate id {candidate_id} is unknown")

            for alias in object_.aliases_from_source:
                if not any(
                    _normalized_contains(source_events[event_id], alias)
                    for event_id in object_.source_event_ids
                ):
                    raise ValueError(f"alias {alias} is not present in the selected source events")

            if object_.canonical_name_source_event_id is not None:
                if object_.canonical_name_source_event_id not in object_.source_event_ids:
                    raise ValueError("canonical name evidence must be one of source_event_ids")
                if object_.canonical_name_source_event_id not in known_events:
                    raise ValueError(
                        f"unknown source event {object_.canonical_name_source_event_id}"
                    )

            if object_.resolution in {"new", "ambiguous"}:
                assert object_.new_canonical_name is not None
                components = _component_count(object_.new_canonical_name)
                if not 1 <= components <= 4:
                    raise ValueError("canonical name must contain between 1 and 4 components")
                if components >= 3:
                    evidence_event_id = object_.canonical_name_source_event_id
                    if evidence_event_id is None:
                        raise ValueError("extended canonical name requires source evidence")
                    if not _normalized_contains(
                        source_events[evidence_event_id],
                        object_.new_canonical_name,
                    ):
                        raise ValueError(
                            "extended canonical name is not present in its source event"
                        )
                elif not any(
                    _normalized_contains(source_events[event_id], object_.new_canonical_name)
                    for event_id in object_.source_event_ids
                ):
                    raise ValueError("new canonical name is not present in the source events")

        for value in self.values:
            for event_id in value.source_event_ids:
                if event_id not in known_events:
                    raise ValueError(f"unknown source event {event_id}")


class LedgerMindContext(ProtocolModel):
    schema_version: Literal[1] = 1
    retrieval_request_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    delivered_value_ids: list[str] = Field(max_length=MAX_CONTEXT_IDS)

    @model_validator(mode="after")
    def validate_context_extension(self) -> LedgerMindContext:
        _require_identifier(self.retrieval_request_id, "retrieval request id")
        for value_id in self.delivered_value_ids:
            _require_identifier(value_id, "delivered value id")
        _validate_unique(self.delivered_value_ids, "delivered_value_ids")
        return self


class RawRoundContextExtension(ProtocolModel):
    ledgermind_context: LedgerMindContext


class RawRoundResolutionExtension(ProtocolModel):
    """The owned ``source.extensions`` wrapper for resolution identity."""

    ledgermind_resolution: LedgerMindResolution


LedgerMindResolutionExtension = RawRoundResolutionExtension


def validate_raw_round_source_extensions(
    extensions: Mapping[str, Any] | RawRoundResolutionExtension,
) -> RawRoundResolutionExtension | None:
    """Validate the owned source extension without discarding other keys."""

    if isinstance(extensions, RawRoundResolutionExtension):
        return extensions
    if not isinstance(extensions, Mapping):
        raise TypeError("RawRound source extensions must be an object")
    if "ledgermind_resolution" not in extensions:
        return None
    return RawRoundResolutionExtension.model_validate(
        {"ledgermind_resolution": extensions["ledgermind_resolution"]}
    )


def validate_raw_round_extensions(
    extensions: Mapping[str, Any] | RawRoundContextExtension | RawRoundResolutionExtension,
) -> RawRoundContextExtension | RawRoundResolutionExtension | None:
    """Validate owned extensions without changing unrelated extensions."""

    if isinstance(extensions, RawRoundContextExtension):
        return extensions
    if isinstance(extensions, RawRoundResolutionExtension):
        return extensions
    if not isinstance(extensions, Mapping):
        raise TypeError("RawRound extensions must be an object")
    resolution = validate_raw_round_source_extensions(extensions)
    if "ledgermind_context" in extensions:
        context = extensions["ledgermind_context"]
        return RawRoundContextExtension.model_validate({"ledgermind_context": context})
    return resolution


class FacetActivation(ProtocolModel):
    facet: Facet
    score: float = Field(ge=0.0, le=1.0)
    embedding_similarity_raw: float = 0.0
    relative_margin: float = Field(default=0.0, ge=0.0, le=1.0)
    lexical_cues: list[str] = Field(
        default_factory=list, max_length=MAX_EXPLANATION_SIGNALS
    )
    signals: list[str] = Field(default_factory=list, max_length=MAX_EXPLANATION_SIGNALS)

    @model_validator(mode="after")
    def validate_activation(self) -> FacetActivation:
        if not math.isfinite(self.embedding_similarity_raw):
            raise ValueError("facet embedding similarity must be finite")
        for cue in self.lexical_cues:
            _require_text(cue, "facet lexical cue", MAX_IDENTIFIER_LENGTH)
        for signal in self.signals:
            _require_text(signal, "facet activation signal", MAX_IDENTIFIER_LENGTH)
        return self


class ScoreComponents(ProtocolModel):
    semantic_similarity: float = Field(ge=0.0, le=1.0)
    semantic_similarity_raw: float = Field(default=0.0, ge=0.0, le=1.0)
    semantic_contribution: float = Field(ge=0.0, le=1.0)
    object_similarity: float = Field(ge=0.0, le=1.0)
    object_similarity_raw: float = Field(default=0.0, ge=0.0, le=1.0)
    primary_object_similarity: float = Field(default=0.0, ge=0.0, le=1.0, exclude_if=lambda value: value == 0.0)
    related_object_similarity: float = Field(default=0.0, ge=0.0, le=1.0, exclude_if=lambda value: value == 0.0)
    related_object_similarity_raw: float = Field(default=0.0, ge=0.0, le=1.0, exclude_if=lambda value: value == 0.0)
    related_object_multiplier: float = Field(default=0.0, ge=0.0, le=1.0, exclude_if=lambda value: value == 0.0)
    object_card_cosine: float = Field(default=0.0, ge=0.0, le=1.0)
    lexical_object_match: float = Field(default=0.0, ge=0.0, le=1.0)
    object_embedding_similarity_raw: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    object_embedding_contribution: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    object_lexical_score: float | None = Field(default=None, ge=0.0, le=1.0)
    object_lexical_contribution: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    object_contribution: float = Field(ge=0.0, le=1.0)
    facet_compatibility: float = Field(ge=0.0, le=1.0)
    facet_compatibility_raw: float = Field(default=0.0, ge=0.0, le=1.0)
    facet_similarity_raw: float | None = Field(default=None, ge=0.0, le=1.0)
    facet_contribution: float = Field(ge=0.0, le=1.0)
    scope_time_compatibility: float = Field(ge=0.0, le=1.0)
    scope_time_contribution: float = Field(ge=0.0, le=1.0)
    context_compatibility: float = Field(ge=0.0, le=1.0)
    context_contribution: float = Field(ge=0.0, le=1.0)
    recency_component: float = Field(ge=0.0, le=1.0)
    recency_contribution: float = Field(ge=0.0, le=1.0)
    support_component: float = Field(ge=0.0, le=1.0)
    support_contribution: float = Field(ge=0.0, le=1.0)
    usage_component: float = Field(ge=0.0, le=1.0)
    usage_contribution: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)


class RetrievalExplanation(ProtocolModel):
    object_reasons: list[ObjectReason] = Field(max_length=MAX_EXPLANATION_REASONS)
    item_facet: Facet
    activated_facets: list[FacetActivation] = Field(max_length=MAX_REQUESTED_FACETS)
    score_components: ScoreComponents

    @model_validator(mode="after")
    def validate_explanation(self) -> RetrievalExplanation:
        _validate_unique(self.object_reasons, "object_reasons")
        facets = [activation.facet for activation in self.activated_facets]
        _validate_unique(facets, "activated_facets facets")
        return self


class RetrievalItem(ProtocolModel):
    value_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    primary_object_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    object_name: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    target_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    target_name: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    target_breadcrumb: list[str] = Field(
        default_factory=list,
        max_length=16,
        exclude_if=lambda value: not value,
    )
    facet: Facet
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    scope_text: str | None = Field(default=None, min_length=1, max_length=MAX_SCOPE_TEXT_LENGTH)
    content_language: str | None = Field(default=None, min_length=1, max_length=32)
    conditions: list[ClaimCondition] = Field(
        default_factory=list,
        max_length=MAX_CLAIM_CONDITIONS,
    )
    source_event_ids: list[str] = Field(min_length=1, max_length=MAX_SOURCE_EVENT_IDS)
    relevance: float = Field(ge=0.0, le=1.0)
    explanation: RetrievalExplanation

    @model_validator(mode="after")
    def validate_item(self) -> RetrievalItem:
        _require_identifier(self.value_id, "value id")
        _require_identifier(self.primary_object_id, "primary object id")
        _require_text(self.object_name, "object name", MAX_IDENTIFIER_LENGTH)
        if self.target_id is not None:
            _require_identifier(self.target_id, "target id")
        if self.target_name is not None:
            _require_text(self.target_name, "target name", MAX_IDENTIFIER_LENGTH)
        if self.content_language is not None:
            _require_text(self.content_language, "content language", 32)
        for condition in self.conditions:
            condition._validate_condition_fields()
        _validate_unique(
            [(condition.source_event_id, condition.surface_text) for condition in self.conditions],
            "conditions",
        )
        for breadcrumb in self.target_breadcrumb:
            _require_text(breadcrumb, "target breadcrumb", MAX_IDENTIFIER_LENGTH)
        _validate_ids(self.source_event_ids, "source_event_ids", MAX_SOURCE_EVENT_IDS)
        if self.explanation.item_facet != self.facet:
            raise ValueError("explanation item_facet must match the item facet")
        return self


class RetrievalFormulaTuning(ProtocolModel):
    semantic: float | None = Field(default=None, ge=0.0, le=1.0)
    object: float | None = Field(default=None, ge=0.0, le=1.0)
    facet: float | None = Field(default=None, ge=0.0, le=1.0)
    scope_time: float | None = Field(default=None, ge=0.0, le=1.0)
    context: float | None = Field(default=None, ge=0.0, le=1.0)
    recency: float | None = Field(default=None, ge=0.0, le=1.0)
    support: float | None = Field(default=None, ge=0.0, le=1.0)
    usage: float | None = Field(default=None, ge=0.0, le=1.0)


class RetrievalTuning(ProtocolModel):
    formula: RetrievalFormulaTuning | None = None
    global_semantic_top: int | None = Field(default=None, ge=1)
    critical_relevance_min: float | None = Field(default=None, ge=0.0, le=1.0)
    min_semantic_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    relative_score_window: float | None = Field(default=None, ge=0.0, le=1.0)
    max_context_items: int | None = Field(default=None, ge=1, le=MAX_RETRIEVAL_ITEMS)
    min_final_score: float | None = Field(default=None, ge=0.0, le=1.0)
    related_object_multiplier: float | None = Field(default=None, ge=0.0, le=1.0)


class RetrievalRequest(ProtocolModel):
    """Core retrieval request with the query embedding supplied by Local."""

    schema_version: Literal[2, 3] = 2
    memory_space_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    query_text: str = Field(min_length=1, max_length=MAX_CONTENT_LENGTH)
    query_embedding: list[float] = Field(min_length=1, max_length=MAX_EMBEDDING_DIMENSIONS)
    embedding_model_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    embedding_model_version: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    limit: int = Field(ge=1, le=MAX_RETRIEVAL_ITEMS)
    base_limit: int | None = Field(default=None, ge=1, le=MAX_RETRIEVAL_ITEMS)
    retrieval_tuning: RetrievalTuning | None = None
    project_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    repository_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    task_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    conversation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_IDENTIFIER_LENGTH,
    )
    target_id: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    target_alias: str | None = Field(default=None, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    query_language: str | None = Field(default=None, min_length=1, max_length=32)
    related_object_ids: list[str] | None = None
    requested_facets: list[Facet] | None = None
    explanation_level: ExplanationLevel = "compact"

    @model_validator(mode="after")
    def validate_request(self) -> RetrievalRequest:
        if any(
            not math.isfinite(component) or abs(component) > MAX_EMBEDDING_ABSOLUTE_VALUE
            for component in self.query_embedding
        ):
            raise ValueError("query_embedding values must be finite and bounded")
        if self.repository_id is not None and self.project_id is None:
            raise ValueError("repository id requires a matching project id")
        if self.base_limit is not None and self.base_limit > self.limit:
            raise ValueError("base_limit must not exceed limit")
        if self.related_object_ids is not None:
            _validate_ids(self.related_object_ids, "related_object_ids", MAX_RELATED_REFS, minimum=0)
        if self.requested_facets is not None:
            if len(self.requested_facets) > MAX_REQUESTED_FACETS:
                raise ValueError(f"requested_facets must not exceed {MAX_REQUESTED_FACETS} entries")
            _validate_unique(self.requested_facets, "requested_facets")
        if self.query_language is not None:
            _require_text(self.query_language, "query language", 32)
        return self


class MemoryInjection(ProtocolModel):
    """Core-rendered, deterministic memory context for agent injection."""

    format: Literal["facet_legend"]
    text: str = Field(max_length=65_536)
    legend: list[str] = Field(max_length=14)
    item_count: int = Field(ge=0, le=MAX_RETRIEVAL_ITEMS)

    @model_validator(mode="after")
    def validate_injection(self) -> MemoryInjection:
        for row in self.legend:
            _require_text(row, "memory injection legend row", 1_024)
        if self.item_count == 0 and self.text:
            raise ValueError("empty retrieval must have empty memory injection text")
        return self


class RetrievalResponse(ProtocolModel):
    schema_version: Literal[2, 3] = 2
    retrieval_request_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    items: list[RetrievalItem] = Field(max_length=MAX_RETRIEVAL_ITEMS)
    target_resolution: dict[str, Any] | None = None
    memory_injection: MemoryInjection | None = None
    retrieval_diagnostics: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_response(self) -> RetrievalResponse:
        _require_identifier(self.retrieval_request_id, "retrieval request id")
        if self.memory_injection is not None and self.memory_injection.item_count != len(
            self.items
        ):
            raise ValueError("memory_injection.item_count must match items")
        if self.retrieval_diagnostics is not None:
            encoded = json.dumps(
                self.retrieval_diagnostics,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(encoded) > 1_048_576:
                raise ValueError("retrieval_diagnostics must not exceed 1 MiB")
        return self


class RecordRetrievalOutcome(ProtocolModel):
    schema_version: Literal[2] = 2
    retrieval_request_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    candidate_value_ids: list[str] = Field(min_length=1, max_length=MAX_RETRIEVAL_OUTCOME_IDS)
    delivered_value_ids: list[str] = Field(max_length=MAX_RETRIEVAL_OUTCOME_IDS)
    created_at: str

    @model_validator(mode="after")
    def validate_outcome(self) -> RecordRetrievalOutcome:
        _parse_rfc3339(self.created_at, "created_at")
        _validate_ids(self.candidate_value_ids, "candidate_value_ids", MAX_RETRIEVAL_OUTCOME_IDS)
        _validate_ids(
            self.delivered_value_ids,
            "delivered_value_ids",
            MAX_RETRIEVAL_OUTCOME_IDS,
            minimum=0,
        )
        if not set(self.delivered_value_ids).issubset(set(self.candidate_value_ids)):
            raise ValueError("delivered_value_ids must be a subset of candidate_value_ids")
        return self


class EmbedResult(ProtocolModel):
    task_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    model_id: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    model_version: str = Field(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
    dimensions: int = Field(ge=1, le=MAX_EMBEDDING_DIMENSIONS)
    vectors: list[list[float]] = Field(min_length=1, max_length=MAX_EMBEDDING_VECTORS)

    @model_validator(mode="after")
    def validate_result(self) -> EmbedResult:
        for index, vector in enumerate(self.vectors):
            if len(vector) != self.dimensions:
                raise ValueError(
                    f"vector {index} dimension {len(vector)} does not match "
                    f"declared dimensions {self.dimensions}"
                )
            if any(
                not math.isfinite(component) or abs(component) > MAX_EMBEDDING_ABSOLUTE_VALUE
                for component in vector
            ):
                raise ValueError(f"vector {index} contains a non-finite or unbounded value")
        return self

    def validate_for_request(self, request: EmbeddingRequest) -> None:
        if len(self.vectors) != len(request.texts):
            raise ValueError(
                f"vectors count {len(self.vectors)} must equal texts count {len(request.texts)}"
            )
        if request.dimensions is not None and self.dimensions != request.dimensions:
            raise ValueError(
                f"dimensions {self.dimensions} must match the requested dimensions "
                f"{request.dimensions}"
            )


def _canonical_payload(payload: object) -> dict[str, Any]:
    if isinstance(payload, ProtocolModel):
        value = payload.model_dump(mode="json", exclude_none=True)
    elif isinstance(payload, Mapping):
        value = dict(payload)
    else:
        raise TypeError("object-facet payload must be an object or ProtocolModel")
    if not isinstance(value, dict):
        raise TypeError("object-facet payload must be an object")
    return value


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        _canonical_payload(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_digest(payload: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


calculate_object_facet_digest = canonical_digest

__all__ = [
    "FACET_VALUES",
    "MAX_CLAIMS",
    "MAX_CLAIM_CONDITIONS",
    "MAX_CLAIM_CONTEXT_ANCHORS",
    "MAX_CLAIM_REFS",
    "MAX_CONTEXT_IDS",
    "MAX_COVERAGE_ENTRIES",
    "MAX_EMBEDDING_DIMENSIONS",
    "MAX_EMBEDDING_TEXTS",
    "MAX_EMBEDDING_VECTORS",
    "MAX_MENTIONS",
    "MAX_MENTION_CANDIDATES",
    "MAX_OUTPUT_TOKENS",
    "MAX_TASK_MESSAGES",
    "OBJECT_REASON_VALUES",
    "ClaimCondition",
    "ClaimCoverage",
    "ClaimExtractionOutput",
    "ClaimSubject",
    "ConditionGrounding",
    "CoverageDisposition",
    "EmbedResult",
    "EmbeddingPurpose",
    "EmbeddingRequest",
    "ExplanationLevel",
    "ExtractedClaim",
    "ExtractedValue",
    "Facet",
    "FacetActivation",
    "GenericExecutionTask",
    "IngestRawRoundRequest",
    "IngestRawRoundResponse",
    "IngestStatus",
    "LedgerMindContext",
    "LedgerMindResolution",
    "LedgerMindResolutionExtension",
    "MentionResolutionInput",
    "ModelRequest",
    "ObjectCandidate",
    "ObjectReason",
    "ObjectResolution",
    "OperationalClaimOutput",
    "OperationalExtractionInput",
    "OperationalExtractionResult",
    "OperationalModelClaim",
    "OperationalModelClaimOutput",
    "OperationalModelCoverage",
    "ProfileSlot",
    "RawRoundContextExtension",
    "RawRoundResolutionExtension",
    "RecordRetrievalOutcome",
    "ResolutionContext",
    "ResolvedObject",
    "ResponseFormat",
    "RetrievalExplanation",
    "RetrievalItem",
    "RetrievalRequest",
    "RetrievalResponse",
    "ScoreComponents",
    "StructuredOutputMode",
    "SubjectGrounding",
    "TaskKind",
    "calculate_object_facet_digest",
    "canonical_digest",
    "canonical_json_bytes",
    "validate_raw_round_extensions",
    "validate_raw_round_source_extensions",
]
