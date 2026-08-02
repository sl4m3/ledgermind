"""Context ranking strategies used by `RetrieveContextHandler`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from application.mappers import RetrieveContextQuery
from domain import KnowledgeItem, Phase
from ports import SearchHit


_PHASE_MULTIPLIER = {
    Phase.PATTERN: 1.0,
    Phase.EMERGENT: 1.1,
    Phase.CANONICAL: 1.2,
}


def _clamp_score(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


@dataclass(frozen=True, slots=True)
class RankedContextItem:
    """Item enriched by deterministic ranking diagnostics."""

    item: KnowledgeItem
    lexical_score: float
    vector_score: float | None
    combined_score: float
    phase_multiplier: float
    score: float


class ContextRanking:
    def __init__(self, lexical_weight: float = 0.55, vector_weight: float = 0.45) -> None:
        if lexical_weight <= 0 or vector_weight < 0 or lexical_weight + vector_weight <= 0:
            raise ValueError("weights must be positive and total > 0")
        self._lexical_weight = lexical_weight
        self._vector_weight = vector_weight

    def _phase_multiplier(self, item: KnowledgeItem) -> float:
        return _PHASE_MULTIPLIER[item.phase]

    def _compute(self, hit: SearchHit, item: KnowledgeItem) -> tuple[float, float, float]:
        lexical = _clamp_score(hit.lexical_score)
        if hit.vector_score is None:
            combined = lexical
            return combined, lexical, 0.0

        vector = _clamp_score(hit.vector_score)
        combined = self._lexical_weight * lexical + self._vector_weight * vector
        return combined, lexical, vector

    def rank(
        self,
        query: RetrieveContextQuery,
        hits: Sequence[SearchHit],
        items: Sequence[KnowledgeItem],
    ) -> list[RankedContextItem]:
        del query

        by_id: dict[str, KnowledgeItem] = {
            item.knowledge_id: item for item in items if item.is_current
        }
        ranked: list[RankedContextItem] = []
        used: set[str] = set()

        for hit in hits:
            if hit.knowledge_id in used:
                continue
            used.add(hit.knowledge_id)

            item = by_id.get(hit.knowledge_id)
            if item is None:
                continue

            combined, lexical, vector = self._compute(hit, item)
            phase_multiplier = self._phase_multiplier(item)
            score = min(1.0, combined * phase_multiplier)
            ranked.append(
                RankedContextItem(
                    item=item,
                    lexical_score=lexical,
                    vector_score=None if hit.vector_score is None else vector,
                    combined_score=combined,
                    phase_multiplier=phase_multiplier,
                    score=score,
                )
            )

        ranked.sort(key=lambda entry: (-entry.score, entry.item.knowledge_id))
        return ranked


__all__ = ["ContextRanking", "RankedContextItem"]
