"""Port definitions should remain abstract and minimal."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

from ledgermind_core.ports import (
    Clock,
    DomainEvent,
    EventRepository,
    IdempotencyRepository,
    IdentifierFactory,
    KnowledgeSearch,
    SearchHit,
    StoredIdempotencyResult,
    UnitOfWork,
    AtomRepository,
    EvidenceRepository,
    KnowledgeRepository,
    RevisionRepository,
)


def test_ports_are_abstract() -> None:
    for port in (
        AtomRepository,
        KnowledgeRepository,
        EvidenceRepository,
        RevisionRepository,
        IdempotencyRepository,
        EventRepository,
        KnowledgeSearch,
        UnitOfWork,
        Clock,
        IdentifierFactory,
    ):
        assert inspect.isabstract(port)


def test_port_dtos_hold_expected_fields() -> None:
    result = StoredIdempotencyResult(
        key="k",
        request_hash="sha256:" + "a" * 64,
        response_json='{"ok":true}',
    )

    assert result.key == "k"

    event = DomainEvent(
        event_id="e1",
        event_type="atom.created",
        aggregate_id="a1",
        memory_space_id="space",
        payload_json='{"event":"x"}',
        occurred_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    assert event.memory_space_id == "space"

    hit = SearchHit(
        knowledge_id="k1",
        lexical_score=0.5,
        vector_score=None,
    )

    assert hit.knowledge_id == "k1"
