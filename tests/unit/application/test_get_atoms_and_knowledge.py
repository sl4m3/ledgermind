"""Tests for isolated read queries."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from application.get_atom import GetAtomHandler, GetAtomQuery
from application.get_knowledge import GetKnowledgeHandler, GetKnowledgeQuery
from domain import (
    Atom,
    AtomContent,
    ExtractionInfo,
    KnowledgeItem,
    Phase,
    SourceReference,
)
from tests.fakes import FakeClock, FakeIdentifierFactory, FakeUnitOfWork


_SPACE = "space_01"
_OTHER_SPACE = "space_02"


def _atom(atom_id: str = "atm_1", memory_space_id: str = _SPACE) -> Atom:
    return Atom(
        atom_id=atom_id,
        memory_space_id=memory_space_id,
        source=SourceReference(
            source_system="hermes",
            source_instance_id="instance",
            source_profile_id="default",
            source_session_id="session",
            source_round_id="round",
            first_message_id=None,
            final_message_id=None,
            message_ids=("m1",),
            source_digest="sha256:" + "a" * 64,
            source_schema_version=1,
            resolver_version=1,
        ),
        content=AtomContent(
            title="title",
            target="target",
            statement="statement",
            rationale="rationale",
            result="result",
        ),
        extraction=ExtractionInfo(
            host="hermes",
            provider="provider",
            model="model",
            prompt_version=1,
            schema_version=1,
            purpose="ledgermind.atom.extract",
        ),
        content_digest="sha256:" + "d" * 64,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def _knowledge(knowledge_id: str = "knw_1", memory_space_id: str = _SPACE) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        memory_space_id=memory_space_id,
        title="title",
        target="target",
        statement="statement",
        rationale="rationale",
        phase=Phase.PATTERN,
        version=1,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def _setup(
    *,
    atom_store=None,
    knowledge_store=None,
) -> tuple[GetAtomHandler, GetKnowledgeHandler, FakeUnitOfWork]:
    uow = FakeUnitOfWork(
        clock=FakeClock(datetime(2026, 8, 1, tzinfo=timezone.utc)),
        atom_store=atom_store,
        knowledge_store=knowledge_store,
    )

    return (
        GetAtomHandler(uow_factory=lambda: uow),
        GetKnowledgeHandler(uow_factory=lambda: uow),
        uow,
    )


def test_get_atom_reads_by_space_and_id() -> None:
    get_atom, get_knowledge, uow = _setup(
        atom_store={_SPACE: {_atom().atom_id: _atom()}, _OTHER_SPACE: {_atom("atm_2", _OTHER_SPACE): _atom("atm_2", _OTHER_SPACE)}}
    )

    result = get_atom.handle(GetAtomQuery(memory_space_id=_SPACE, atom_id=_atom().atom_id))

    assert result == _atom()
    assert uow.commit_count == 0


def test_get_atom_returns_none_if_not_in_memory_space() -> None:
    get_atom, _, uow = _setup(
        atom_store={_SPACE: {_atom("atm_2").atom_id: _atom("atm_2")}}
    )

    assert get_atom.handle(GetAtomQuery(memory_space_id=_OTHER_SPACE, atom_id="atm_2")) is None
    assert uow.rollback_count == 0
    assert uow.commit_count == 0


def test_get_atom_missing() -> None:
    get_atom, _, _ = _setup(atom_store={_SPACE: {_atom("atm_2").atom_id: _atom("atm_2")}})

    assert get_atom.handle(GetAtomQuery(memory_space_id=_SPACE, atom_id="atm_99")) is None


def test_get_atom_query_requires_memory_space_id() -> None:
    with pytest.raises(ValueError, match="memory_space_id must not be empty"):
        GetAtomQuery(memory_space_id="", atom_id="atm_1")


def test_get_atom_query_requires_atom_id() -> None:
    with pytest.raises(ValueError, match="atom_id must not be empty"):
        GetAtomQuery(memory_space_id=_SPACE, atom_id="")


def test_get_knowledge_reads_by_space_and_id() -> None:
    get_atom, get_knowledge, uow = _setup(
        knowledge_store={
            _SPACE: {_knowledge().knowledge_id: _knowledge()},
            _OTHER_SPACE: {_knowledge("knw_2", _OTHER_SPACE): _knowledge("knw_2", _OTHER_SPACE)},
        }
    )

    _ = get_atom.handle(GetAtomQuery(memory_space_id=_SPACE, atom_id=_atom().atom_id))
    result = get_knowledge.handle(
        GetKnowledgeQuery(memory_space_id=_SPACE, knowledge_id=_knowledge().knowledge_id)
    )

    assert result == _knowledge()
    assert uow.commit_count == 0


def test_get_knowledge_returns_none_if_not_in_memory_space() -> None:
    get_atom, get_knowledge, _ = _setup(
        knowledge_store={_SPACE: {_knowledge("knw_2").knowledge_id: _knowledge("knw_2")}}
    )

    assert (
        get_knowledge.handle(GetKnowledgeQuery(memory_space_id=_OTHER_SPACE, knowledge_id="knw_2"))
        is None
    )


def test_get_knowledge_missing() -> None:
    _, get_knowledge, _ = _setup(knowledge_store={_SPACE: {_knowledge().knowledge_id: _knowledge()}})

    assert get_knowledge.handle(GetKnowledgeQuery(memory_space_id=_SPACE, knowledge_id="knw_99")) is None


def test_get_knowledge_query_requires_memory_space_id() -> None:
    with pytest.raises(ValueError, match="memory_space_id must not be empty"):
        GetKnowledgeQuery(memory_space_id="", knowledge_id="knw_1")


def test_get_knowledge_query_requires_knowledge_id() -> None:
    with pytest.raises(ValueError, match="knowledge_id must not be empty"):
        GetKnowledgeQuery(memory_space_id=_SPACE, knowledge_id="")
