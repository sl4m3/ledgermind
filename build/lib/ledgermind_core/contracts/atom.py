"""Public contract models for atom ingestion."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import SHA256_CHECKSUM_PATTERN, ContractModel


class SourceReference(ContractModel):
    source_system: Literal["hermes", "legacy_import"]
    source_instance_id: str = Field(min_length=1, max_length=200)
    source_profile_id: str = Field(min_length=1, max_length=200)
    source_session_id: str = Field(min_length=1, max_length=300)
    source_round_id: str = Field(min_length=1, max_length=300)
    first_message_id: str | None = None
    final_message_id: str | None = None
    message_ids: list[str] = Field(default_factory=list, max_length=1000)
    source_digest: str = Field(pattern=SHA256_CHECKSUM_PATTERN)
    source_schema_version: int = Field(ge=1)
    resolver_version: int = Field(ge=1)


class AtomContent(ContractModel):
    title: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=240)
    statement: str = Field(min_length=1, max_length=20_000)
    rationale: str = Field(default="", max_length=40_000)
    result: str = Field(default="", max_length=20_000)
    artifacts: list[str] = Field(default_factory=list, max_length=500)


class ExtractionInfo(ContractModel):
    host: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="", max_length=200)
    model: str = Field(default="", max_length=300)
    prompt_version: int = Field(ge=1)
    schema_version: int = Field(ge=1)
    purpose: str = Field(default="ledgermind.atom.extract", max_length=200)


class IngestAtomRequest(ContractModel):
    api_version: Literal["1"] = "1"
    idempotency_key: str = Field(pattern=SHA256_CHECKSUM_PATTERN)
    memory_space_id: str = Field(min_length=1, max_length=200)
    source: SourceReference
    extraction: ExtractionInfo
    atom: AtomContent


class IngestAtomResult(ContractModel):
    api_version: Literal["1"] = "1"
    atom_id: str
    knowledge_id: str
    knowledge_version: int = Field(ge=1)
    phase: Literal["pattern", "emergent", "canonical"]
    duplicate: bool
    projections_pending: bool


__all__ = [
    "AtomContent",
    "ExtractionInfo",
    "IngestAtomRequest",
    "IngestAtomResult",
    "SourceReference",
]
