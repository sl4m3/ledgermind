"""Unit of Work fake coordinating transactional behavior for repository fakes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Self

from domain import Atom, KnowledgeEvidence, KnowledgeItem, KnowledgeRevision
from ports import (
    Clock,
    UnitOfWork,
)
from ports.repository_ports import (
    DomainEvent,
    EventRepository,
    StoredIdempotencyResult,
)
from tests.fakes.clock import FakeClock
from tests.fakes.identifiers import FakeIdentifierFactory
from tests.fakes.repositories import (
    FakeAtomRepository,
    FakeEvidenceRepository,
    FakeIdempotencyRepository,
    FakeKnowledgeRepository,
    FakeRevisionRepository,
)
from tests.fakes.search import FakeKnowledgeSearch


class FakeEventRepository(EventRepository):
    def __init__(self, fail_steps: Iterable[str] | None = None) -> None:
        self._fail_steps = set(fail_steps or [])
        self._events: list[DomainEvent] = []

    def _fail(self, step: str) -> None:
        if step in self._fail_steps or f"events.{step}" in self._fail_steps:
            raise RuntimeError(f"fake repository step failed: events.{step}")

    def add(self, event: DomainEvent) -> None:
        self._fail("add")
        self._events.append(event)

    @property
    def stored_events(self) -> Sequence[DomainEvent]:
        self._fail("stored_events")
        return list(self._events)


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
        self._clock = clock or FakeClock(datetime.min.replace(tzinfo=timezone.utc))
        self._identifiers = FakeIdentifierFactory()

        self._atoms = FakeAtomRepository(atom_store, fail_steps=self._fail_steps)
        self._knowledge = FakeKnowledgeRepository(knowledge_store, fail_steps=self._fail_steps)
        self._evidence = FakeEvidenceRepository(evidence_store, fail_steps=self._fail_steps)
        self._revisions = FakeRevisionRepository(revision_store, fail_steps=self._fail_steps)
        self._idempotency = FakeIdempotencyRepository(
            idempotency_store,
            fail_steps=self._fail_steps,
        )
        self._events = FakeEventRepository(fail_steps=self._fail_steps)
        self._search = FakeKnowledgeSearch(search_items or [])

        self._committed_events: list[DomainEvent] = []
        self._committed_count = 0
        self._rollback_count = 0

    @property
    def atoms(self) -> FakeAtomRepository:
        return self._atoms

    @property
    def knowledge(self) -> FakeKnowledgeRepository:
        return self._knowledge

    @property
    def evidence(self) -> FakeEvidenceRepository:
        return self._evidence

    @property
    def revisions(self) -> FakeRevisionRepository:
        return self._revisions

    @property
    def idempotency(self) -> FakeIdempotencyRepository:
        return self._idempotency

    @property
    def events(self) -> FakeEventRepository:
        return self._events

    @property
    def search(self) -> FakeKnowledgeSearch:
        return self._search

    @search.setter
    def search(self, value: FakeKnowledgeSearch) -> None:
        self._search = value

    @property
    def clock(self) -> FakeClock:
        return self._clock

    @property
    def identifiers(self) -> FakeIdentifierFactory:
        return self._identifiers

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

    def __enter__(self) -> Self:
        self._fail("enter")
        self._entered = True
        for repo in (
            self.atoms,
            self.knowledge,
            self.evidence,
            self.revisions,
            self.idempotency,
        ):
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
        for repo in (
            self.atoms,
            self.knowledge,
            self.evidence,
            self.revisions,
            self.idempotency,
        ):
            repo.commit()
        self._committed_events = list(self.events.stored_events)
        self._committed_count += 1

    def rollback(self) -> None:
        self._fail("rollback")
        for repo in (
            self._atoms,
            self._knowledge,
            self._evidence,
            self._revisions,
            self._idempotency,
        ):
            repo.rollback()
        self._events = FakeEventRepository()
        self._rollback_count += 1


__all__ = ["FakeEventRepository", "FakeUnitOfWork"]
