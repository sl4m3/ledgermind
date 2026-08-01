"""Tests for canonical domain events."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from ledgermind_core.domain import events


def test_events_have_stable_serialized_names() -> None:
    created_at = datetime(2026, 8, 1, tzinfo=timezone.utc)

    emitted_events = [
        events.AtomCreated(
            event_id="e1",
            happened_at=created_at,
            atom_id="atom-1",
        ),
        events.KnowledgeCreated(
            event_id="e2",
            happened_at=created_at,
            knowledge_id="knowledge-1",
            source_atom_id="atom-1",
        ),
        events.KnowledgeSuperseded(
            event_id="e3",
            happened_at=created_at,
            previous_knowledge_id="knowledge-1",
            next_knowledge_id="knowledge-2",
            by_atom_id="atom-2",
        ),
        events.KnowledgeDeleted(
            event_id="e4",
            happened_at=created_at,
            knowledge_id="knowledge-2",
            by_atom_id="atom-3",
        ),
    ]

    assert emitted_events[0].event_name == "atom.created"
    assert emitted_events[1].event_name == "knowledge.created"
    assert emitted_events[2].event_name == "knowledge.superseded"
    assert emitted_events[3].event_name == "knowledge.deleted"


def test_events_have_immutable_payloads() -> None:
    evt = events.KnowledgeCreated(
        event_id="e5",
        happened_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        knowledge_id="knowledge-1",
        source_atom_id="atom-1",
    )

    with pytest.raises(FrozenInstanceError):
        evt.knowledge_id = "other"


def test_events_require_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError):
        events.AtomCreated(
            event_id="e6",
            happened_at=datetime.now(),
            atom_id="atom-1",
        )
