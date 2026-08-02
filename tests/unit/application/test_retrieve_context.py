"""Tests for context retrieval use case."""

from __future__ import annotations

from datetime import datetime, timezone

from application.mappers import RetrieveContextQuery
from application.ranking import ContextRanking
from application.retrieve_context import RetrieveContextHandler
from domain import KnowledgeEvidence, KnowledgeItem
from domain.phase import Phase
from ports import SearchHit
from tests.fakes import FakeClock, FakeUnitOfWork


_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)
_SPACE = "space_01"
_OTHER = "space_02"


def _knowledge(
    *,
    knowledge_id: str,
    phase: Phase = Phase.PATTERN,
    memory_space_id: str = _SPACE,
    superseded_by_id: str | None = None,
    deleted_at: datetime | None = None,
) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        memory_space_id=memory_space_id,
        title=f"title_{knowledge_id}",
        target=f"target_{knowledge_id}",
        statement=f"statement_{knowledge_id}",
        rationale=f"rationale_{knowledge_id}",
        phase=phase,
        version=1,
        created_at=_NOW,
        updated_at=_NOW,
        superseded_by_id=superseded_by_id,
        deleted_at=deleted_at,
    )


def _evidence(knowledge_id: str, atom_id: str) -> KnowledgeEvidence:
    return KnowledgeEvidence(
        knowledge_id=knowledge_id,
        atom_id=atom_id,
        relation="origin",
        created_at=_NOW,
    )


class _FakeSearch:
    def __init__(self, hits: list[SearchHit]) -> None:
        self._hits = hits

    def search(self, memory_space_id: str, query: str, limit: int) -> list[SearchHit]:
        return self._hits[:limit]


def _setup(
    *,
    knowledge_store,
    hits: list[SearchHit] | None = None,
    evidence=None,
):
    uow = FakeUnitOfWork(
        clock=FakeClock(_NOW),
        knowledge_store=knowledge_store,
        evidence_store=evidence,
    )
    if hits is not None:
        uow.search = _FakeSearch(hits)

    handler = RetrieveContextHandler(
        uow_factory=lambda: uow,
        ranking=ContextRanking(),
    )
    return handler, uow


def test_retrieve_context_does_not_return_other_spaces() -> None:
    query = RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=3)
    handler, uow = _setup(
        knowledge_store={
            _SPACE: {
                "k1": _knowledge(knowledge_id="k1"),
            },
            _OTHER: {
                "k2": _knowledge(
                    knowledge_id="k2",
                    memory_space_id=_OTHER,
                ),
            },
        },
        hits=[
            SearchHit(knowledge_id="k2", lexical_score=1.0, vector_score=None),
            SearchHit(knowledge_id="k1", lexical_score=0.4, vector_score=None),
        ],
    )

    result = handler.handle(query)

    assert [item.knowledge_id for item in result.items] == ["k1"]
    assert uow.commit_count == 0
    assert uow.rollback_count == 0


def test_retrieve_context_filters_deleted_and_superseded_items() -> None:
    handler, _ = _setup(
        knowledge_store={
            _SPACE: {
                "k1": _knowledge(knowledge_id="k1"),
                "k2": _knowledge(knowledge_id="k2", superseded_by_id="k3"),
                "k3": _knowledge(knowledge_id="k3", deleted_at=_NOW),
            }
        },
        hits=[
            SearchHit(knowledge_id="k1", lexical_score=1.0, vector_score=None),
            SearchHit(knowledge_id="k2", lexical_score=0.9, vector_score=None),
            SearchHit(knowledge_id="k3", lexical_score=0.8, vector_score=None),
        ],
    )
    result = handler.handle(RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=5))

    assert [item.knowledge_id for item in result.items] == ["k1"]


def test_retrieve_context_uses_fts_only_when_vector_is_missing() -> None:
    handler, _ = _setup(
        knowledge_store={
            _SPACE: {"k1": _knowledge(knowledge_id="k1")},
        },
        hits=[
            SearchHit(knowledge_id="k1", lexical_score=0.5, vector_score=None),
        ],
    )
    result = handler.handle(RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=5))

    assert result.items[0].score == 0.5


def test_retrieve_context_uses_hybrid_scoring_when_vector_present() -> None:
    handler, _ = _setup(
        knowledge_store={
            _SPACE: {
                "k1": _knowledge(knowledge_id="k1", phase=Phase.CANONICAL),
                "k2": _knowledge(knowledge_id="k2", phase=Phase.PATTERN),
            }
        },
        hits=[
            SearchHit(knowledge_id="k1", lexical_score=0.7, vector_score=0.9),
            SearchHit(knowledge_id="k2", lexical_score=0.6, vector_score=0.1),
        ],
    )
    result = handler.handle(RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=5))

    assert [item.knowledge_id for item in result.items] == ["k1", "k2"]
    expected_k1 = min(1.0, (0.55 * 0.7 + 0.45 * 0.9) * 1.2)
    expected_k2 = min(1.0, (0.55 * 0.6 + 0.45 * 0.1) * 1.0)
    assert result.items[0].score == expected_k1
    assert result.items[1].score == expected_k2


def test_retrieve_context_order_is_explainable_and_stable_by_knowledge_id() -> None:
    handler, _ = _setup(
        knowledge_store={
            _SPACE: {
                "k_b": _knowledge(knowledge_id="k_b"),
                "k_a": _knowledge(knowledge_id="k_a"),
                "k_c": _knowledge(knowledge_id="k_c"),
            },
        },
        hits=[
            SearchHit(knowledge_id="k_b", lexical_score=0.5, vector_score=None),
            SearchHit(knowledge_id="k_a", lexical_score=0.5, vector_score=None),
            SearchHit(knowledge_id="k_c", lexical_score=0.9, vector_score=None),
        ],
    )
    result = handler.handle(RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=5))

    assert [item.knowledge_id for item in result.items] == ["k_c", "k_a", "k_b"]


def test_retrieve_context_phase_multiplier_affects_order_before_tie_break() -> None:
    handler, _ = _setup(
        knowledge_store={
            _SPACE: {
                "k_pattern": _knowledge(knowledge_id="k_pattern", phase=Phase.PATTERN),
                "k_canonical": _knowledge(knowledge_id="k_canonical", phase=Phase.CANONICAL),
            }
        },
        hits=[
            SearchHit(knowledge_id="k_pattern", lexical_score=0.95, vector_score=None),
            SearchHit(knowledge_id="k_canonical", lexical_score=0.95, vector_score=None),
        ],
    )
    result = handler.handle(RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=5))

    assert result.items[0].knowledge_id == "k_canonical"
    assert result.items[1].knowledge_id == "k_pattern"


def test_retrieve_context_min_phase_filtering_applies() -> None:
    handler, _ = _setup(
        knowledge_store={
            _SPACE: {
                "k_pattern": _knowledge(knowledge_id="k_pattern", phase=Phase.PATTERN),
                "k_emergent": _knowledge(knowledge_id="k_emergent", phase=Phase.EMERGENT),
                "k_canonical": _knowledge(knowledge_id="k_canonical", phase=Phase.CANONICAL),
            },
        },
        hits=[
            SearchHit(knowledge_id="k_pattern", lexical_score=1.0, vector_score=None),
            SearchHit(knowledge_id="k_emergent", lexical_score=0.9, vector_score=None),
            SearchHit(knowledge_id="k_canonical", lexical_score=0.8, vector_score=None),
        ],
    )
    result = handler.handle(
        RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=5, min_phase="emergent")
    )

    assert [item.knowledge_id for item in result.items] == ["k_emergent", "k_canonical"]


def test_retrieve_context_limits_result_size_by_query_limit() -> None:
    handler, _ = _setup(
        knowledge_store={
            _SPACE: {
                "k1": _knowledge(knowledge_id="k1"),
                "k2": _knowledge(knowledge_id="k2"),
                "k3": _knowledge(knowledge_id="k3"),
            },
        },
        hits=[
            SearchHit(knowledge_id="k1", lexical_score=1.0, vector_score=None),
            SearchHit(knowledge_id="k2", lexical_score=0.9, vector_score=None),
            SearchHit(knowledge_id="k3", lexical_score=0.8, vector_score=None),
        ],
    )
    result = handler.handle(RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=1))

    assert len(result.items) == 1
    assert result.items[0].knowledge_id == "k1"


def test_retrieve_context_does_not_write() -> None:
    handler, uow = _setup(
        knowledge_store={
            _SPACE: {"k1": _knowledge(knowledge_id="k1")},
        },
        hits=[SearchHit(knowledge_id="k1", lexical_score=1.0, vector_score=None)],
    )

    handler.handle(RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=5))

    assert uow.commit_count == 0
    assert uow.rollback_count == 0


def test_retrieve_context_rank_tie_is_stable_by_knowledge_id() -> None:
    handler, _ = _setup(
        knowledge_store={
            _SPACE: {
                "zeta": _knowledge(knowledge_id="zeta"),
                "alpha": _knowledge(knowledge_id="alpha"),
                "beta": _knowledge(knowledge_id="beta"),
            },
        },
        hits=[
            SearchHit(knowledge_id="zeta", lexical_score=0.4, vector_score=0.6),
            SearchHit(knowledge_id="alpha", lexical_score=0.4, vector_score=0.6),
            SearchHit(knowledge_id="beta", lexical_score=0.4, vector_score=0.6),
        ],
    )
    result = handler.handle(RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=5))

    assert [item.knowledge_id for item in result.items] == ["alpha", "beta", "zeta"]


def test_retrieve_context_enriches_output_with_evidence_stats() -> None:
    handler, _ = _setup(
        knowledge_store={
            _SPACE: {
                "k1": _knowledge(knowledge_id="k1"),
                "k2": _knowledge(knowledge_id="k2"),
            }
        },
        hits=[
            SearchHit(knowledge_id="k1", lexical_score=1.0, vector_score=None),
            SearchHit(knowledge_id="k2", lexical_score=0.9, vector_score=None),
        ],
        evidence=[
            _evidence("k1", "atm_1"),
            _evidence("k1", "atm_2"),
            _evidence("k1", "atm_3"),
            _evidence("k2", "atm_4"),
        ],
    )
    result = handler.handle(RetrieveContextQuery(memory_space_id=_SPACE, query="statement", limit=5))

    assert result.items[0].evidence_count == 3
    assert result.items[0].source_atom_ids == ["atm_1", "atm_2", "atm_3"]
    assert result.items[1].evidence_count == 1
    assert result.items[1].source_atom_ids == ["atm_4"]
