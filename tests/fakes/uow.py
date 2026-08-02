"""Unit of Work fake coordinating transactional behavior for repository fakes."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping, Sequence

from domain import Atom, KnowledgeEvidence, KnowledgeItem, KnowledgeRevision
from ports import (
    Clock,
    IdempotencyRepository,
    KnowledgeSearch,
    UnitOfWork,
)
from ports.repository_ports import (
    StoredIdempotencyResult,
    DomainEvent,
    EventRepository,
)
from tests.fakes.repositories import (
    FakeAtomRepository,
    FakeEvidenceRepository,
    FakeIdempotencyRepository,
    FakeKnowledgeRepository,
    FakeRevisionRepository,
)
from tests.fakes.search import FakeKnowledgeSearch
from tests.fakes.identifiers import FakeIdentifierFactory
from tests.fakes.clock import FakeClock


class FakeEventRepository(EventRepository):
    def __init__(self, fail_steps: Iterable[str] | None = None) -> None:
        self._fail_steps = set(fail_steps or [])
        self.events: list[DomainEvent] = []

    def _fail(self, step: str) -> None:
        if step in self._fail_steps or f"events.{step}" in self._fail_steps:
            raise RuntimeError(f"fake repository step failed: events.{step}")

    def add(self, event: DomainEvent) -> None:
        self._fail("add")
        self.events.append(event)


class FakeUnitOfWork(UnitOfWork):
    def __init__(
        self,
        *,
        atom_store: Mapping[str, Mapping[str, Atom]] | None = None,
        knowledge_store: Mapping[str, Mapping[str, KnowledgeItem]] | None = None,
        evidence_store: Sequence[KnowledgeEvidence] | None = None,
        revision_store: Sequence[KnowledgeRevision] | None = None,
        idempotency_store: Mapping[str, StoredIdempotencyResult] | None = None,
        search_items: Sequence[KnowledgeItem] | None = None,
        clock: Clock | None = None,
        fail_steps: Iterable[str] | None = None,
    ) -> None:
        self._fail_steps = set(fail_steps or [])
        self.clock = clock or FakeClock(datetime.min)
        self.identifiers = FakeIdentifierFactory()

        self.atoms = FakeAtomRepository(atom_store, fail_steps=self._fail_steps)
        self.knowledge = FakeKnowledgeRepository(knowledge_store, fail_steps=self._fail_steps)
        self.evidence = FakeEvidenceRepository(evidence_store, fail_steps=self._fail_steps)
        self.revisions = FakeRevisionRepository(revision_store, fail_steps=self._fail_steps)
        self.idempotency = FakeIdempotencyRepository(
            idempotency_store,
            fail_steps=self._fail_steps,
        )
        self.events = FakeEventRepository(fail_steps=self._fail_steps)
        self.search = FakeKnowledgeSearch(search_items or [])

        self._committed_events = list(self.events.events)
        self._entered = False
        self._committed_count = 0
        self._rollback_count = 0

    def _fail(self, step: str) -> None:
        if step in self._fail_steps or f"uow.{step}" in self._fail_steps:
            raise RuntimeError(f"fake uow step failed: {step}")

    @property
    def committed_events(self) -> list[DomainEvent]:
        return list(self._committed_events)

    @property
    def commit_count(self) -> int:
        return self._committed_count

    @property
    def rollback_count(self) -> int:
        return self._rollback_count

    def __enter__(self) -> "FakeUnitOfWork":
        self._fail("enter")
        self._entered = True
        for repo in (self.atoms, self.knowledge, self.evidence, self.revisions, self.idempotency):
            repo.begin()
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        if exc is not None:
            self.rollback()

    def commit(self) -> None:
        self._fail("commit")
        for repo in (self.atoms, self.knowledge, self.evidence, self.revisions, self.idempotency):
            repo.commit()
        self._committed_events = list(self.events.events)
        self._committed_count += 1

    def rollback(self) -> None:
        self._fail("rollback")
        for repo in (self.atoms, self.knowledge, self.evidence, self.revisions, self.idempotency):
            repo.rollback()
        self.events = FakeEventRepository()
        self._rollback_count += 1
