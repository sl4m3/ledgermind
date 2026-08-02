"""Knowledge aggregate root for LedgerMind core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .phase import Phase


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    knowledge_id: str
    memory_space_id: str
    title: str
    target: str
    statement: str
    rationale: str
    phase: Phase
    version: int
    created_at: datetime
    updated_at: datetime
    superseded_by_id: str | None = None
    deleted_at: datetime | None = None

    @property
    def is_current(self) -> bool:
        return self.superseded_by_id is None and self.deleted_at is None

    def __post_init__(self) -> None:
        if not self.knowledge_id:
            raise ValueError("knowledge_id must not be empty")
        if not self.memory_space_id:
            raise ValueError("memory_space_id must not be empty")
        if self.version < 1:
            raise ValueError("version must be >= 1")

        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")

        if self.superseded_by_id == self.knowledge_id:
            raise ValueError("knowledge cannot supersede itself")

        if self.deleted_at is not None and self.deleted_at.tzinfo is None:
            raise ValueError("deleted_at must be timezone-aware")


__all__ = ["KnowledgeItem"]
