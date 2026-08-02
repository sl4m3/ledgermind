"""Tests for transactional in-memory fakes used by core services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain import Atom, AtomContent, ExtractionInfo, SourceReference
from domain.knowledge import KnowledgeItem
from domain.phase import Phase
from ports.repository_ports import DomainEvent
from tests.fakes.clock import FakeClock
from tests.fakes.identifiers import FakeIdentifierFactory
from tests.fakes.search import FakeKnowledgeSearch
from tests.fakes.uow import FakeUnitOfWork


def _atom() -> Atom:
    return Atom(
        atom_id="atm_1",
        memory_space_id="space",
        source=SourceReference(
            source_system="hermes",
            source_instance_id="instance",
            source_profile_id="default",
            source_session_id="session",
            source_round_id="round",
            first_message_id=None,
            final_message_id=None,
            message_ids=(),
            source_digest="sha256:" + "a" * 64,
            source_schema_version=1,
            resolver_version=1,
        ),
        content=AtomContent(
            title="t",
            target="g",
            statement="s",
            rationale="r",
            result="x",
        ),
        extraction=ExtractionInfo(
            host="hermes",
            provider="provider",
            model="model",
            prompt_version=1,
            schema_version=1,
            purpose="ledgermind.atom.extract",
        ),
        content_digest="sha256:" + "b" * 64,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def _knowledge() -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id="k1",
        memory_space_id="space",
        title="t",
        target="g",
        statement="s",
        rationale="r",
        phase=Phase.PATTERN,
        version=1,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_fake_uow_does_not_publish_without_commit() -> None:
    uow = FakeUnitOfWork()
    with uow:
        uow.atoms.add(_atom())
        assert "space" not in uow.atoms.committed()
    assert uow.atoms.committed() == {}


def test_fake_uow_commit_and_rollback_are_tracked() -> None:
    uow = FakeUnitOfWork()
    with uow:
        uow.knowledge.add(_knowledge())
        uow.commit()

    assert uow.commit_count == 1
    assert uow.knowledge.committed() == {"space": {"k1": _knowledge()}}
    assert uow.rollback_count == 0


def test_fake_uow_rollback_reverts_uncommitted_state() -> None:
    uow = FakeUnitOfWork()
    with uow:
        uow.knowledge.add(_knowledge())
        uow.rollback()

    assert uow.rollback_count == 1
    assert uow.knowledge.committed() == {}


def test_fake_uow_failure_is_injectable() -> None:
    uow = FakeUnitOfWork(fail_steps={"knowledge.add"})
    with pytest.raises(RuntimeError, match="fake repository step failed"), uow:
        uow.knowledge.add(_knowledge())


def test_fake_uow_enter_failure_is_injectable() -> None:
    uow = FakeUnitOfWork(fail_steps={"uow.enter"})
    with pytest.raises(RuntimeError, match="fake uow step failed"), uow:
        pass


def test_fake_event_add_failure_is_injectable() -> None:
    uow = FakeUnitOfWork(fail_steps={"events.add"})
    with pytest.raises(RuntimeError, match="fake repository step failed"), uow:
        uow.events.add(
            DomainEvent(
                event_id="evt_1",
                event_type="atom_ingested",
                aggregate_id="atm_1",
                memory_space_id="space",
                payload_json='{"ok": true}',
                occurred_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            )
        )


def test_fake_clock_is_deterministic() -> None:
    clock = FakeClock(datetime(2026, 8, 1, tzinfo=timezone.utc))
    assert clock.now() == datetime(2026, 8, 1, tzinfo=timezone.utc)
    clock.tick(timedelta(minutes=1))
    assert clock.now() == datetime(2026, 8, 1, 0, 1, tzinfo=timezone.utc)


def test_fake_identifier_factory_is_deterministic() -> None:
    ids = FakeIdentifierFactory()
    assert ids.new_atom_id() == "atm_000001"
    assert ids.new_knowledge_id() == "knw_000001"


def test_fake_search_limits_results() -> None:
    item = _knowledge()
    search = FakeKnowledgeSearch([item, _knowledge()])
    results = search.search("space", "t", limit=1)
    assert len(results) == 1
    assert results[0].knowledge_id == "k1"
