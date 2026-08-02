"""Context retrieval use case for LedgerMind core."""

from __future__ import annotations

from collections.abc import Callable

from application.mappers import RetrieveContextQuery
from application.ranking import ContextRanking
from contracts import ContextItem, RetrieveContextResult
from domain import Phase
from ports import UnitOfWork

_PHASE_ORDER = {
    Phase.PATTERN: 0,
    Phase.EMERGENT: 1,
    Phase.CANONICAL: 2,
}


class RetrieveContextHandler:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        ranking: ContextRanking | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._ranking = ranking or ContextRanking()

    def _min_phase_rank(self, value: str | None) -> int | None:
        if value is None:
            return None
        return _PHASE_ORDER[Phase(value)]

    def _is_visible(self, phase: Phase, min_phase: str | None) -> bool:
        min_rank = self._min_phase_rank(min_phase)
        if min_rank is None:
            return True
        return _PHASE_ORDER[phase] >= min_rank

    def handle(self, query: RetrieveContextQuery) -> RetrieveContextResult:
        search_limit = max(query.limit * 5, 50)
        with self._uow_factory() as uow:
            hits = uow.search.search(
                memory_space_id=query.memory_space_id,
                query=query.query,
                limit=search_limit,
            )

            knowledge_ids = tuple(hit.knowledge_id for hit in hits)
            knowledge_items = [
                item
                for item in uow.knowledge.get_many(query.memory_space_id, knowledge_ids)
                if item.is_current and self._is_visible(item.phase, query.min_phase)
            ]

            ranked = self._ranking.rank(query, hits, knowledge_items)

            items = []
            for scored in ranked[: query.limit]:
                evidence_count = uow.evidence.count_for_knowledge(
                    query.memory_space_id,
                    scored.item.knowledge_id,
                )
                source_atom_ids = uow.evidence.list_atom_ids(
                    query.memory_space_id,
                    scored.item.knowledge_id,
                )
                items.append(
                    ContextItem(
                        knowledge_id=scored.item.knowledge_id,
                        title=scored.item.title,
                        target=scored.item.target,
                        statement=scored.item.statement,
                        rationale=scored.item.rationale,
                        phase=scored.item.phase.value,
                        score=scored.score,
                        evidence_count=evidence_count,
                        source_atom_ids=source_atom_ids,
                    )
                )

            return RetrieveContextResult(api_version="1", items=items)


__all__ = ["RetrieveContextHandler"]
