"""Search fake implementation."""

from __future__ import annotations

from collections.abc import Sequence

from ledgermind_core.domain import KnowledgeItem
from ledgermind_core.ports import KnowledgeSearch, SearchHit


class FakeKnowledgeSearch(KnowledgeSearch):
    def __init__(self, knowledge_items: Sequence[KnowledgeItem] | None = None) -> None:
        self._knowledge_items = list(knowledge_items or [])

    def search(
        self,
        memory_space_id: str,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        query_lower = query.lower()
        hits: list[SearchHit] = []
        for item in self._knowledge_items:
            if item.memory_space_id != memory_space_id:
                continue
            haystack = f"{item.title} {item.target} {item.statement} {item.rationale}".lower()
            if query_lower in haystack:
                hits.append(
                    SearchHit(
                        knowledge_id=item.knowledge_id,
                        lexical_score=1.0,
                        vector_score=None,
                    )
                )

        return hits[:limit]
