"""Atom domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .source_reference import SourceReference


@dataclass(frozen=True, slots=True)
class AtomContent:
    title: str
    target: str
    statement: str
    rationale: str
    result: str
    artifacts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.target.strip():
            raise ValueError("target must not be empty")
        if not self.statement.strip():
            raise ValueError("statement must not be empty")

        if len(self.title) > 240:
            raise ValueError("title is too long")
        if len(self.target) > 240:
            raise ValueError("target is too long")

        if self.rationale is None:
            raise ValueError("rationale must not be None")
        if self.result is None:
            raise ValueError("result must not be None")

        if not isinstance(self.artifacts, tuple):
            object.__setattr__(self, "artifacts", tuple(self.artifacts))


@dataclass(frozen=True, slots=True)
class ExtractionInfo:
    host: str
    provider: str
    model: str
    prompt_version: int
    schema_version: int
    purpose: str

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("host must not be empty")
        if not self.provider and self.provider != "":
            raise ValueError("provider must be a string")
        if not self.model and self.model != "":
            raise ValueError("model must be a string")
        if self.prompt_version < 1:
            raise ValueError("prompt_version must be >= 1")
        if self.schema_version < 1:
            raise ValueError("schema_version must be >= 1")


@dataclass(frozen=True, slots=True)
class Atom:
    atom_id: str
    memory_space_id: str
    source: SourceReference
    content: AtomContent
    extraction: ExtractionInfo
    content_digest: str
    created_at: datetime
    supersedes_atom_id: str | None = None

    def __post_init__(self) -> None:
        if not self.atom_id:
            raise ValueError("atom_id must not be empty")
        if not self.memory_space_id:
            raise ValueError("memory_space_id must not be empty")
        if self.source is None:
            raise ValueError("source must not be None")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.supersedes_atom_id == self.atom_id:
            raise ValueError("atom cannot supersede itself")
