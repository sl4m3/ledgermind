"""Knowledge read use case for LedgerMind core."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ledgermind_core.domain import KnowledgeItem
from ledgermind_core.ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class GetKnowledgeQuery:
    memory_space_id: str
    knowledge_id: str

    def __post_init__(self) -> None:
        if not self.memory_space_id:
            raise ValueError("memory_space_id must not be empty")
        if not self.knowledge_id:
            raise ValueError("knowledge_id must not be empty")


class GetKnowledgeHandler:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def handle(self, query: GetKnowledgeQuery) -> KnowledgeItem | None:
        with self._uow_factory() as uow:
            return uow.knowledge.get(query.memory_space_id, query.knowledge_id)


__all__ = [
    "GetKnowledgeHandler",
    "GetKnowledgeQuery",
]
