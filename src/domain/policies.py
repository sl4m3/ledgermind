"""Knowledge evolution policy primitives for LedgerMind core."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .atom import Atom
from .knowledge import KnowledgeItem


class EvolutionDecision(ABC):
    """Marker base class for knowledge-evolution decisions."""


@dataclass(frozen=True, slots=True)
class CreateNewPattern(EvolutionDecision):
    title: str
    target: str
    statement: str
    rationale: str


class KnowledgeEvolutionPolicy(ABC):
    @abstractmethod
    def decide(
        self,
        atom: Atom,
        candidates: tuple[KnowledgeItem, ...],
    ) -> EvolutionDecision:
        """Choose evolution decision for a new atom."""


class IsolatedPatternPolicy(KnowledgeEvolutionPolicy):
    def decide(
        self,
        atom: Atom,
        candidates: tuple[KnowledgeItem, ...],
    ) -> EvolutionDecision:
        del candidates

        return CreateNewPattern(
            title=atom.content.title,
            target=atom.content.target,
            statement=atom.content.statement,
            rationale=atom.content.rationale,
        )


__all__ = [
    "EvolutionDecision",
    "CreateNewPattern",
    "KnowledgeEvolutionPolicy",
    "IsolatedPatternPolicy",
]
