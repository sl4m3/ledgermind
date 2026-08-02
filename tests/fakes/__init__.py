"""Test fakes for LedgerMind core."""

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
from tests.fakes.uow import FakeEventRepository, FakeUnitOfWork

__all__ = [
    "FakeAtomRepository",
    "FakeClock",
    "FakeEventRepository",
    "FakeEvidenceRepository",
    "FakeIdempotencyRepository",
    "FakeIdentifierFactory",
    "FakeKnowledgeRepository",
    "FakeKnowledgeSearch",
    "FakeRevisionRepository",
    "FakeUnitOfWork",
]
