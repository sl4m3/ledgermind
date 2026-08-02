"""Tests for knowledge entity invariants."""

from datetime import datetime, timedelta, timezone

import pytest

from ledgermind_core.domain import knowledge as knowledge_module
from ledgermind_core.domain.phase import Phase

KnowledgeItem = knowledge_module.KnowledgeItem


def _base_times():
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    updated_at = created_at + timedelta(minutes=1)
    return created_at, updated_at


def test_phase_values_are_strict() -> None:
    assert {Phase.PATTERN.value, Phase.EMERGENT.value, Phase.CANONICAL.value} == {
        "pattern",
        "emergent",
        "canonical",
    }


def test_version_starts_from_one() -> None:
    created_at, updated_at = _base_times()
    item = KnowledgeItem(
        knowledge_id="k1",
        memory_space_id="space",
        title="t",
        target="tt",
        statement="s",
        rationale="r",
        phase=Phase.PATTERN,
        version=1,
        created_at=created_at,
        updated_at=updated_at,
    )

    assert item.version == 1


def test_knowledge_requires_memory_space() -> None:
    with pytest.raises(ValueError):
        KnowledgeItem(
            knowledge_id="k1",
            memory_space_id="",
            title="t",
            target="tt",
            statement="s",
            rationale="r",
            phase=Phase.PATTERN,
            version=1,
            created_at=_base_times()[0],
            updated_at=_base_times()[1],
        )


def test_knowledge_timestamps_must_be_timezone_aware() -> None:
    created_at, updated_at = _base_times()

    with pytest.raises(ValueError):
        KnowledgeItem(
            knowledge_id="k1",
            memory_space_id="space",
            title="t",
            target="tt",
            statement="s",
            rationale="r",
            phase=Phase.PATTERN,
            version=1,
            created_at=datetime(2020, 1, 1),  # noqa: DTZ001
            updated_at=updated_at,
        )

    with pytest.raises(ValueError):
        KnowledgeItem(
            knowledge_id="k1",
            memory_space_id="space",
            title="t",
            target="tt",
            statement="s",
            rationale="r",
            phase=Phase.PATTERN,
            version=1,
            created_at=created_at,
            updated_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )


def test_is_current_structural() -> None:
    created_at, updated_at = _base_times()
    active = KnowledgeItem(
        knowledge_id="k1",
        memory_space_id="space",
        title="t",
        target="tt",
        statement="s",
        rationale="r",
        phase=Phase.PATTERN,
        version=1,
        created_at=created_at,
        updated_at=updated_at,
    )
    superseded = KnowledgeItem(
        knowledge_id="k1",
        memory_space_id="space",
        title="t",
        target="tt",
        statement="s",
        rationale="r",
        phase=Phase.PATTERN,
        version=1,
        created_at=created_at,
        updated_at=updated_at,
        superseded_by_id="k2",
    )
    deleted = KnowledgeItem(
        knowledge_id="k2",
        memory_space_id="space",
        title="t",
        target="tt",
        statement="s",
        rationale="r",
        phase=Phase.PATTERN,
        version=1,
        created_at=created_at,
        updated_at=updated_at,
        deleted_at=updated_at,
    )

    assert active.is_current
    assert not superseded.is_current
    assert not deleted.is_current


def test_invalid_updates_and_supersession_rules() -> None:
    created_at, updated_at = _base_times()

    with pytest.raises(ValueError):
        KnowledgeItem(
            knowledge_id="k1",
            memory_space_id="space",
            title="t",
            target="tt",
            statement="s",
            rationale="r",
            phase=Phase.PATTERN,
            version=0,
            created_at=created_at,
            updated_at=updated_at,
        )

    with pytest.raises(ValueError):
        KnowledgeItem(
            knowledge_id="k1",
            memory_space_id="space",
            title="t",
            target="tt",
            statement="s",
            rationale="r",
            phase=Phase.PATTERN,
            version=1,
            created_at=updated_at,
            updated_at=created_at,
        )

    with pytest.raises(ValueError):
        KnowledgeItem(
            knowledge_id="k1",
            memory_space_id="space",
            title="t",
            target="tt",
            statement="s",
            rationale="r",
            phase=Phase.PATTERN,
            version=1,
            created_at=created_at,
            updated_at=updated_at,
            superseded_by_id="k1",
        )


def test_domain_model_does_not_keep_legacy_state_fields() -> None:
    # ensures old v3 state fields are not silently introduced in model
    assert not hasattr(KnowledgeItem, "status")
    assert not hasattr(KnowledgeItem, "vitality")
    assert not hasattr(KnowledgeItem, "confidence")
