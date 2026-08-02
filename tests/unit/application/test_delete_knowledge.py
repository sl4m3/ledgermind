"""Tests for knowledge logical deletion application flow."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from application.delete_knowledge import (
    DeleteKnowledgeCommand,
    DeleteKnowledgeError,
    DeleteKnowledgeHandler,
)
from domain import KnowledgeItem, Phase
from domain.events import KnowledgeDeleted
from tests.fakes import FakeClock, FakeUnitOfWork

_SPACE = "space_01"
_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _knowledge(
    knowledge_id: str,
    *,
    memory_space_id: str = _SPACE,
    version: int = 1,
    deleted_at: datetime | None = None,
    superseded_by_id: str | None = None,
) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        memory_space_id=memory_space_id,
        title=f"title_{knowledge_id}",
        target=f"target_{knowledge_id}",
        statement=f"statement_{knowledge_id}",
        rationale=f"rationale_{knowledge_id}",
        phase=Phase.PATTERN,
        version=version,
        created_at=_NOW,
        updated_at=_NOW,
        superseded_by_id=superseded_by_id,
        deleted_at=deleted_at,
    )


def _command(
    *,
    knowledge_id: str = "knw_1",
    expected_version: int = 1,
    cause_atom_id: str = "atm_1",
) -> DeleteKnowledgeCommand:
    return DeleteKnowledgeCommand(
        memory_space_id=_SPACE,
        knowledge_id=knowledge_id,
        expected_version=expected_version,
        cause_atom_id=cause_atom_id,
    )


def _setup(
    *,
    knowledge_store,
    fail_steps: set[str] | None = None,
) -> tuple[DeleteKnowledgeHandler, FakeUnitOfWork]:
    clock = FakeClock(_NOW)
    uow = FakeUnitOfWork(clock=clock, knowledge_store=knowledge_store, fail_steps=fail_steps)
    handler = DeleteKnowledgeHandler(
        uow_factory=lambda: uow,
        clock=clock,
        identifiers=uow.identifiers,
    )
    return handler, uow


def test_delete_knowledge_marks_deleted_and_records_revision_and_event() -> None:
    initial_knowledge = _knowledge("knw_1", version=1)
    handler, uow = _setup(knowledge_store={_SPACE: {initial_knowledge.knowledge_id: initial_knowledge}})
    command = _command(knowledge_id="knw_1")

    result = handler.handle(command)

    assert result.knowledge_id == "knw_1"
    assert result.version == 2
    assert result.deleted_at == _NOW.isoformat()

    committed = uow.knowledge.committed()[_SPACE]["knw_1"]
    assert committed.deleted_at == _NOW
    assert committed.version == 2
    assert committed.superseded_by_id is None

    revisions = uow.revisions.committed()
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision.knowledge_id == "knw_1"
    assert revision.version == 2
    assert revision.event_type == KnowledgeDeleted.EVENT_NAME
    assert revision.snapshot["deleted_at"] == _NOW.isoformat()

    events = uow.events.stored_events
    assert len(events) == 1
    assert events[0].event_type == KnowledgeDeleted.EVENT_NAME
    assert events[0].aggregate_id == "knw_1"
    assert events[0].memory_space_id == _SPACE
    assert events[0].occurred_at == _NOW
    payload = json.loads(events[0].payload_json)
    assert payload["event_type"] == KnowledgeDeleted.EVENT_NAME
    assert payload["knowledge_id"] == "knw_1"
    assert payload["by_atom_id"] == command.cause_atom_id
    assert uow.commit_count == 1


def test_delete_knowledge_fails_when_knowledge_not_found() -> None:
    handler, uow = _setup(knowledge_store={_SPACE: {"other": _knowledge("other")}})

    with pytest.raises(DeleteKnowledgeError, match="knowledge not found"):
        handler.handle(_command(knowledge_id="knw_1"))

    assert uow.commit_count == 0
    assert uow.rollback_count == 1
    assert uow.revisions.committed() == []
    assert uow.events.stored_events == []


def test_delete_knowledge_fails_when_knowledge_from_another_memory_space() -> None:
    handler, uow = _setup(
        knowledge_store={
            "other_space": {"knw_1": _knowledge("knw_1", memory_space_id="other_space")}
        }
    )
    with pytest.raises(DeleteKnowledgeError, match="knowledge not found"):
        handler.handle(_command(knowledge_id="knw_1"))

    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_delete_knowledge_fails_when_knowledge_already_deleted() -> None:
    deleted = _NOW
    stored = {_SPACE: {"knw_1": _knowledge("knw_1", deleted_at=deleted)}}
    handler, uow = _setup(knowledge_store=stored)

    with pytest.raises(DeleteKnowledgeError, match="already deleted"):
        handler.handle(_command(knowledge_id="knw_1"))

    assert uow.commit_count == 0
    assert uow.rollback_count == 1


def test_delete_knowledge_fails_when_version_mismatch() -> None:
    stored = {_SPACE: {"knw_1": _knowledge("knw_1", version=2)}}
    handler, uow = _setup(knowledge_store=stored)

    with pytest.raises(DeleteKnowledgeError, match="expected version mismatch"):
        handler.handle(_command(knowledge_id="knw_1", expected_version=1))

    assert uow.commit_count == 0
    assert uow.rollback_count == 1


@pytest.mark.parametrize(
    "fail_step",
    [
        "knowledge.update",
        "revision.add",
        "events.add",
        "commit",
    ],
)
def test_delete_knowledge_rolls_back_on_repository_failure(fail_step: str) -> None:
    stored = {_SPACE: {"knw_1": _knowledge("knw_1", version=1)}}
    handler, uow = _setup(knowledge_store=stored, fail_steps={fail_step})

    with pytest.raises(RuntimeError):
        handler.handle(_command(knowledge_id="knw_1"))

    assert uow.commit_count == 0
    assert uow.rollback_count == 1
    assert uow.knowledge.committed() == stored
    assert uow.revisions.committed() == []
    assert uow.events.stored_events == []
