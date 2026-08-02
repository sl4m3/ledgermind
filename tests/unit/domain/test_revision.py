"""Tests for knowledge revision model invariants."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from domain.revision import KnowledgeRevision


def _base_time():
    return datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_knowledge_revision_snapshots_are_normalized_to_deterministic_json() -> None:
    revision = KnowledgeRevision.from_snapshot(
        revision_id="rev-1",
        knowledge_id="kn-1",
        version=3,
        event_type="knowledge.created",
        snapshot={"title": "A", "statement": "S", "meta": {"b": 2, "a": 1}},
        cause_atom_id="atom-1",
        created_at=_base_time(),
    )

    assert revision.snapshot_json == json.dumps(
        {"title": "A", "statement": "S", "meta": {"a": 1, "b": 2}},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def test_knowledge_revision_snapshot_is_not_reference_to_mutable_map() -> None:
    source_snapshot = {"title": "A", "statement": "S"}
    revision = KnowledgeRevision.from_snapshot(
        revision_id="rev-2",
        knowledge_id="kn-1",
        version=1,
        event_type="knowledge.updated",
        snapshot=source_snapshot,
        cause_atom_id="atom-1",
        created_at=_base_time(),
    )

    source_snapshot["title"] = "changed"
    assert revision.snapshot["title"] == "A"


def test_knowledge_revision_validates_json_and_time() -> None:
    with pytest.raises(ValueError):
        KnowledgeRevision(
            revision_id="rev-3",
            knowledge_id="kn-1",
            version=1,
            event_type="knowledge.created",
            snapshot_json="{",
            cause_atom_id=None,
            created_at=_base_time(),
        )

    with pytest.raises(ValueError):
        KnowledgeRevision(
            revision_id="rev-4",
            knowledge_id="kn-1",
            version=0,
            event_type="knowledge.created",
            snapshot_json='{"title":"A"}',
            cause_atom_id=None,
            created_at=_base_time(),
        )

    with pytest.raises(ValueError):
        KnowledgeRevision(
            revision_id="rev-5",
            knowledge_id="kn-1",
            version=1,
            event_type="knowledge.created",
            snapshot_json='{"title":"A"}',
            cause_atom_id=None,
            created_at=datetime(2020, 1, 1),  # noqa: DTZ001
        )


def test_knowledge_revision_version_is_required() -> None:
    revision = KnowledgeRevision(
        revision_id="rev-6",
        knowledge_id="kn-1",
        version=1,
        event_type="knowledge.created",
        snapshot_json='{"title":"A"}',
        cause_atom_id=None,
        created_at=_base_time(),
    )

    assert revision.version == 1
