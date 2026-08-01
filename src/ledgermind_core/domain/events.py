"""Canonical domain events used by the core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from .identifiers import AtomId, EventId, KnowledgeId


@dataclass(frozen=True, slots=True)
class _BaseDomainEvent:
    event_id: EventId
    happened_at: datetime
    EVENT_NAME: ClassVar[str] = "core.domain.event"

    def __post_init__(self) -> None:
        if self.happened_at.tzinfo is None:
            raise ValueError("happened_at must be timezone-aware")

    @property
    def event_name(self) -> str:
        return self.EVENT_NAME


@dataclass(frozen=True, slots=True)
class AtomCreated(_BaseDomainEvent):
    EVENT_NAME: ClassVar[str] = "atom.created"
    atom_id: AtomId


@dataclass(frozen=True, slots=True)
class KnowledgeCreated(_BaseDomainEvent):
    EVENT_NAME: ClassVar[str] = "knowledge.created"
    knowledge_id: KnowledgeId
    source_atom_id: AtomId


@dataclass(frozen=True, slots=True)
class KnowledgeSuperseded(_BaseDomainEvent):
    EVENT_NAME: ClassVar[str] = "knowledge.superseded"
    previous_knowledge_id: KnowledgeId
    next_knowledge_id: KnowledgeId
    by_atom_id: AtomId


@dataclass(frozen=True, slots=True)
class KnowledgeDeleted(_BaseDomainEvent):
    EVENT_NAME: ClassVar[str] = "knowledge.deleted"
    knowledge_id: KnowledgeId
    by_atom_id: AtomId


__all__ = [
    "_BaseDomainEvent",
    "AtomCreated",
    "KnowledgeCreated",
    "KnowledgeSuperseded",
    "KnowledgeDeleted",
]
