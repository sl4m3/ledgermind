"""Port interfaces for persistence and supporting infrastructure."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Optional, Type

from domain import (
    Atom,
    KnowledgeEvidence,
    KnowledgeItem,
    KnowledgeRevision,
)


@dataclass(frozen=True, slots=True)
class StoredIdempotencyResult:
    key: str
    request_hash: str
    response_json: str


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_id: str
    event_type: str
    aggregate_id: str
    memory_space_id: str
    payload_json: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class SearchHit:
    knowledge_id: str
    lexical_score: float
    vector_score: float | None


class UnitOfWork(ABC):
    atoms: "AtomRepository"
    knowledge: "KnowledgeRepository"
    evidence: "EvidenceRepository"
    revisions: "RevisionRepository"
    idempotency: "IdempotencyRepository"
    events: "EventRepository"
    search: "KnowledgeSearch"
    clock: "Clock"
    identifiers: "IdentifierFactory"

    @abstractmethod
    def __enter__(self) -> "UnitOfWork": ...

    @abstractmethod
    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...


class AtomRepository(ABC):
    @abstractmethod
    def get(self, memory_space_id: str, atom_id: str) -> Atom | None: ...

    @abstractmethod
    def find_by_source_version(
        self,
        memory_space_id: str,
        source_round_key: str,
        prompt_version: int,
        schema_version: int,
    ) -> Atom | None: ...

    @abstractmethod
    def add(self, atom: Atom) -> None: ...


class KnowledgeRepository(ABC):
    @abstractmethod
    def get(self, memory_space_id: str, knowledge_id: str) -> KnowledgeItem | None: ...

    @abstractmethod
    def add(self, item: KnowledgeItem) -> None: ...

    @abstractmethod
    def update(self, item: KnowledgeItem, expected_version: int) -> None: ...

    @abstractmethod
    def get_many(
        self,
        memory_space_id: str,
        knowledge_ids: tuple[str, ...],
    ) -> list[KnowledgeItem]: ...


class EvidenceRepository(ABC):
    @abstractmethod
    def add(self, link: KnowledgeEvidence) -> None: ...

    @abstractmethod
    def count_for_knowledge(self, memory_space_id: str, knowledge_id: str) -> int: ...

    @abstractmethod
    def list_atom_ids(self, memory_space_id: str, knowledge_id: str) -> list[str]: ...


class RevisionRepository(ABC):
    @abstractmethod
    def add(self, item: KnowledgeRevision) -> None: ...

    @abstractmethod
    def list_for_knowledge(
        self,
        memory_space_id: str,
        knowledge_id: str,
    ) -> list[KnowledgeRevision]: ...


class IdempotencyRepository(ABC):
    @abstractmethod
    def get(self, key: str) -> StoredIdempotencyResult | None: ...

    @abstractmethod
    def add(self, result: StoredIdempotencyResult) -> None: ...


class EventRepository(ABC):
    @abstractmethod
    def add(self, event: DomainEvent) -> None: ...


class KnowledgeSearch(ABC):
    @abstractmethod
    def search(
        self,
        memory_space_id: str,
        query: str,
        limit: int,
    ) -> list[SearchHit]: ...


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...


class IdentifierFactory(ABC):
    @abstractmethod
    def new_atom_id(self) -> str: ...

    @abstractmethod
    def new_knowledge_id(self) -> str: ...

    @abstractmethod
    def new_revision_id(self) -> str: ...

    @abstractmethod
    def new_event_id(self) -> str: ...


__all__ = [
    "AtomRepository",
    "KnowledgeRepository",
    "EvidenceRepository",
    "RevisionRepository",
    "KnowledgeSearch",
    "SearchHit",
    "IdempotencyRepository",
    "StoredIdempotencyResult",
    "EventRepository",
    "DomainEvent",
    "Clock",
    "IdentifierFactory",
    "UnitOfWork",
]
