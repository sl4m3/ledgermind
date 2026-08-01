"""Test fakes for LedgerMind core."""

from tests.fakes.clock import FakeClock
from tests.fakes.identifiers import FakeIdentifierFactory
from tests.fakes.search import FakeKnowledgeSearch
from tests.fakes.uow import FakeEventRepository, FakeUnitOfWork
from tests.fakes.repositories import (
    FakeAtomRepository,
    FakeEvidenceRepository,
    FakeIdempotencyRepository,
    FakeKnowledgeRepository,
    FakeRevisionRepository,
)

__all__ = [
    "FakeClock",
    "FakeIdentifierFactory",
    "FakeKnowledgeSearch",
    "FakeUnitOfWork",
    "FakeEventRepository",
    "FakeAtomRepository",
    "FakeKnowledgeRepository",
    "FakeEvidenceRepository",
    "FakeRevisionRepository",
    "FakeIdempotencyRepository",
]
