"""Property-based tests for LedgerMind core search invariants."""

from __future__ import annotations

from datetime import datetime, timezone

from ledgermind_core.domain.knowledge import KnowledgeItem
from ledgermind_core.domain.phase import Phase
from tests.fakes.search import FakeKnowledgeSearch


def test_fts_search_returns_empty_for_empty_index() -> None:
    repository = FakeKnowledgeSearch()
    hits = repository.search(memory_space_id="space_1", query="missing", limit=10)
    assert hits == []


def test_fts_search_matches_title_and_statement() -> None:
    repository = FakeKnowledgeSearch(
        knowledge_items=[
            KnowledgeItem(
                knowledge_id="knw_000001",
                memory_space_id="space_1",
                title="LedgerMind alpha release",
                target="release",
                statement="ship alpha",
                rationale="get feedback",
                phase=Phase.PATTERN,
                version=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ],
    )
    hits = repository.search(memory_space_id="space_1", query="alpha", limit=10)
    assert len(hits) == 1
    assert hits[0].knowledge_id == "knw_000001"


def test_fts_search_supports_partial_match() -> None:
    repository = FakeKnowledgeSearch(
        knowledge_items=[
            KnowledgeItem(
                knowledge_id="knw_000002",
                memory_space_id="space_1",
                title="LedgerMind architecture",
                target="architecture",
                statement="refactor architecture",
                rationale="maintainability",
                phase=Phase.PATTERN,
                version=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ],
    )
    hits = repository.search(memory_space_id="space_1", query="arch", limit=10)
    assert len(hits) == 1
    assert hits[0].knowledge_id == "knw_000002"


def test_fts_search_is_case_insensitive() -> None:
    repository = FakeKnowledgeSearch(
        knowledge_items=[
            KnowledgeItem(
                knowledge_id="knw_000003",
                memory_space_id="space_1",
                title="LedgerMind Architecture",
                target="architecture",
                statement="refactor architecture",
                rationale="maintainability",
                phase=Phase.PATTERN,
                version=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ],
    )
    hits = repository.search(memory_space_id="space_1", query="ARCHITECTURE", limit=10)
    assert len(hits) == 1
    assert hits[0].knowledge_id == "knw_000003"
