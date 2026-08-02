"""Tests for identifier value primitives."""

import inspect
from typing import NewType

from domain.identifiers import (
    AtomId,
    EventId,
    KnowledgeId,
    MemorySpaceId,
    RevisionId,
)


def test_identifiers_are_str_based_newtype_factories() -> None:
    identifiers = (AtomId, KnowledgeId, MemorySpaceId, RevisionId, EventId)

    for identifier in identifiers:
        assert isinstance(identifier, type(NewType("x", str)))
        assert isinstance(identifier("value"), str)
        assert identifier("value") == "value"
        assert callable(identifier)


def test_identifier_type_names() -> None:
    assert AtomId.__name__ == "AtomId"
    assert KnowledgeId.__name__ == "KnowledgeId"
    assert MemorySpaceId.__name__ == "MemorySpaceId"
    assert RevisionId.__name__ == "RevisionId"
    assert EventId.__name__ == "EventId"


def test_no_identifier_generation_inside_identifiers_module() -> None:
    from domain import identifiers

    source = inspect.getsource(identifiers)
    assert "uuid" not in source.lower()
    assert "random" not in source.lower()
    assert "getrand" not in source.lower()
    assert "secrets" not in source.lower()
