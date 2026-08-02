"""Evidence links between knowledge items and atoms."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

from .identifiers import AtomId, KnowledgeId


class EvidenceRelation(str, Enum):
    ORIGIN = "origin"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REFINES = "refines"


@dataclass(frozen=True, slots=True)
class KnowledgeEvidence:
    knowledge_id: KnowledgeId
    atom_id: AtomId
    relation: EvidenceRelation
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.knowledge_id:
            raise ValueError("knowledge_id must not be empty")
        if not self.atom_id:
            raise ValueError("atom_id must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")


def assert_has_origin_relation(evidences: Iterable[KnowledgeEvidence]) -> None:
    if not any(e.relation == EvidenceRelation.ORIGIN for e in evidences):
        raise ValueError("knowledge creation requires at least one ORIGIN evidence")


__all__ = ["EvidenceRelation", "KnowledgeEvidence", "assert_has_origin_relation"]
