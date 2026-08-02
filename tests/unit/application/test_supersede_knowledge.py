"""Tests for manual knowledge supersession application flow."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ledgermind_core.application.mappers import SupersedeKnowledgeCommand
from ledgermind_core.application.supersede_knowledge import (
    SupersedeKnowledgeError,
    SupersedeKnowledgeHandler,
)
from ledgermind_core.domain import KnowledgeItem
from ledgermind_core.domain.events import KnowledgeCreated, KnowledgeSuperseded
from ledgermind_core.domain.phase import Phase
from tests.fakes import FakeClock, FakeUnitOfWork

_SPACE = "space_01"
_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _knowledge(
    knowledge_id: str,
    *,
    memory_space_id: str = _SPACE,
    phase: Phase = Phase.PATTERN,
    version: int = 1,
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
        version=version,
        created_at=_NOW,
        updated_at=_NOW,
        superseded_by_id=superseded_by_id,
        deleted_at=deleted_at,
    )


def _command(
    *,
    old_knowledge_ids: tuple[str, ...],
    expected_versions: dict[str, int] | None = None,
    cause_atom_id: str | None = None,
) -> SupersedeKnowledgeCommand:
    if expected_versions is None:
        expected_versions = {knowledge_id: 1 for knowledge_id in old_knowledge_ids}

    return SupersedeKnowledgeCommand(
        memory_space_id=_SPACE,
        old_knowledge_ids=old_knowledge_ids,
        replacement_title="Updated title",
        replacement_target="target_replacement",
        replacement_statement="Updated statement",
        replacement_rationale="Updated rationale",
        cause_atom_id=cause_atom_id,
        expected_versions=expected_versions,
    )


def _setup(
    *,
    knowledge_store,
    fail_steps: set[str] | None = None,
) -> tuple[SupersedeKnowledgeHandler, FakeUnitOfWork]:
    clock = FakeClock(_NOW)
    uow = FakeUnitOfWork(clock=clock, knowledge_store=knowledge_store, fail_steps=fail_steps)
    handler = SupersedeKnowledgeHandler(
        uow_factory=lambda: uow,
        clock=clock,
        identifiers=uow.identifiers,
    )
    return handler, uow


def test_supersede_knowledge_creates_replacement_and_marks_old_superseded() -> None:
    old_knowledge = [
        _knowledge("knw_1", version=3),
        _knowledge("knw_2", version=1),
    ]
    handler, uow = _setup(
        knowledge_store={_SPACE: {k.knowledge_id: k for k in old_knowledge}}
    )
    command = _command(
        old_knowledge_ids=tuple(k.knowledge_id for k in old_knowledge),
        expected_versions={"knw_1": 3, "knw_2": 1},
    )

    result = handler.handle(command)

    assert result.replacement_version == 1
    assert result.superseded_knowledge_ids == command.old_knowledge_ids

    committed = uow.knowledge.committed()[_SPACE]
    replacement = committed[result.replacement_knowledge_id]
    assert replacement.phase == Phase.CANONICAL
    assert replacement.version == 1
    assert replacement.memory_space_id == _SPACE

    assert committed["knw_1"].superseded_by_id == result.replacement_knowledge_id
    assert committed["knw_1"].version == 4
    assert committed["knw_2"].superseded_by_id == result.replacement_knowledge_id
    assert committed["knw_2"].version == 2

    assert len(uow.revisions.committed()) == 3
    assert len(uow.events.stored_events) == 3
    assert uow.events.stored_events[0].event_type == KnowledgeCreated.EVENT_NAME
    assert uow.events.stored_events[1].event_type == KnowledgeSuperseded.EVENT_NAME
    assert uow.events.stored_events[2].event_type == KnowledgeSuperseded.EVENT_NAME
    payload = json.loads(uow.events.stored_events[1].payload_json)
    assert payload["previous_knowledge_id"] == "knw_1"
    assert payload["next_knowledge_id"] == result.replacement_knowledge_id
    assert uow.commit_count == 1


def test_supersede_knowledge_fails_when_old_knowledge_missing() -> None:
    stored = {_SPACE: {"knw_1": _knowledge("knw_1")}}
    handler, uow = _setup(knowledge_store=stored)

    with pytest.raises(SupersedeKnowledgeError, match="unknown old knowledge ids"):
        handler.handle(_command(old_knowledge_ids=("knw_1", "knw_missing")))

    assert uow.commit_count == 0
    assert uow.rollback_count == 1
    assert uow.knowledge.committed() == stored
    assert uow.revisions.committed() == []
    assert uow.events.stored_events == []


def test_supersede_knowledge_fails_when_knowledge_from_other_memory_space() -> None:
    stored = {
        _SPACE: {"knw_1": _knowledge("knw_1")},
        "other_space": {"knw_2": _knowledge("knw_2", memory_space_id="other_space")},
    }
    handler, uow = _setup(knowledge_store=stored)

    with pytest.raises(SupersedeKnowledgeError, match="unknown old knowledge ids|same memory_space_id"):
        handler.handle(
            _command(
                old_knowledge_ids=("knw_1", "knw_2"),
                expected_versions={"knw_1": 1, "knw_2": 1},
            )
        )

    assert uow.rollback_count == 1
    assert uow.commit_count == 0


def test_supersede_knowledge_fails_when_old_knowledge_not_current() -> None:
    stored = {
        _SPACE: {
            "knw_1": _knowledge("knw_1", superseded_by_id="knw_999"),
            "knw_2": _knowledge("knw_2"),
        },
    }
    handler, uow = _setup(knowledge_store=stored)

    with pytest.raises(SupersedeKnowledgeError, match="already superseded"):
        handler.handle(_command(old_knowledge_ids=("knw_1", "knw_2"), expected_versions={"knw_1": 1, "knw_2": 1}))

    assert uow.rollback_count == 1
    assert uow.commit_count == 0


def test_supersede_knowledge_fails_when_expected_version_mismatch() -> None:
    stored = {_SPACE: {"knw_1": _knowledge("knw_1", version=2)}}
    handler, uow = _setup(knowledge_store=stored)

    with pytest.raises(SupersedeKnowledgeError, match="expected version mismatch"):
        handler.handle(_command(old_knowledge_ids=("knw_1",), expected_versions={"knw_1": 1}))

    assert uow.rollback_count == 1
    assert uow.commit_count == 0


def test_supersede_knowledge_fails_when_replacement_id_collides() -> None:
    stored = {_SPACE: {"knw_000001": _knowledge("knw_000001")}}
    handler, uow = _setup(knowledge_store=stored)

    with pytest.raises(SupersedeKnowledgeError, match="overlaps"):
        handler.handle(_command(old_knowledge_ids=("knw_000001",), expected_versions={"knw_000001": 1}))

    assert uow.rollback_count == 1
    assert uow.commit_count == 0


def test_supersede_knowledge_fails_on_supersession_cycle() -> None:
    stored = {
        _SPACE: {
            "knw_1": _knowledge("knw_1", superseded_by_id="knw_2"),
            "knw_2": _knowledge("knw_2", superseded_by_id="knw_1"),
        },
    }
    handler, uow = _setup(knowledge_store=stored)

    with pytest.raises(SupersedeKnowledgeError, match="cycle detected"):
        handler.handle(_command(old_knowledge_ids=("knw_1", "knw_2"), expected_versions={"knw_1": 1, "knw_2": 1}))

    assert uow.rollback_count == 1
    assert uow.commit_count == 0


def test_supersede_knowledge_rolls_back_on_repository_failure() -> None:
    stored = {_SPACE: {"knw_1": _knowledge("knw_1")}}
    handler, uow = _setup(knowledge_store=stored, fail_steps={"knowledge.update"})

    with pytest.raises(RuntimeError):
        handler.handle(_command(old_knowledge_ids=("knw_1",), expected_versions={"knw_1": 1}))

    assert uow.rollback_count == 1
    assert uow.commit_count == 0
    assert uow.revisions.committed() == []
    assert len(uow.events.stored_events) == 0
