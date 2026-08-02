"""Public contract models for context retrieval."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import ContractModel


class RetrieveContextRequest(ContractModel):
    api_version: Literal["1"] = "1"
    memory_space_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=20_000)
    limit: int = Field(default=5, ge=1, le=50)
    min_phase: Literal["pattern", "emergent", "canonical"] | None = None


class ContextItem(ContractModel):
    knowledge_id: str
    title: str
    target: str
    statement: str
    rationale: str
    phase: Literal["pattern", "emergent", "canonical"]
    score: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(ge=0)
    source_atom_ids: list[str]


class RetrieveContextResult(ContractModel):
    api_version: Literal["1"] = "1"
    items: list[ContextItem]


__all__ = [
    "ContextItem",
    "RetrieveContextRequest",
    "RetrieveContextResult",
]
