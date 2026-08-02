"""Tests for atom entity invariants."""

from datetime import datetime, timezone

import pytest

from domain.atom import Atom, AtomContent, ExtractionInfo
from domain.source_reference import SourceReference


def _source() -> SourceReference:
    return SourceReference(
        source_system="hermes",
        source_instance_id="inst",
        source_profile_id="prof",
        source_session_id="sess",
        source_round_id="round",
        first_message_id=None,
        final_message_id=None,
        message_ids=(),
        source_digest="sha256:" + "a" * 64,
        source_schema_version=1,
        resolver_version=1,
    )


def _content() -> AtomContent:
    return AtomContent(
        title="title",
        target="target",
        statement="statement",
        rationale="rationale",
        result="result",
    )


def _extraction() -> ExtractionInfo:
    return ExtractionInfo(
        host="host",
        provider="prov",
        model="model",
        prompt_version=1,
        schema_version=1,
        purpose="ledgermind.atom.extract",
    )


def test_atom_requires_memory_space() -> None:
    with pytest.raises(ValueError):
        Atom(
            atom_id="atm",
            memory_space_id="",
            source=_source(),
            content=_content(),
            extraction=_extraction(),
            content_digest="d",
            created_at=datetime.now(timezone.utc),
        )


def test_atom_requires_source_reference() -> None:
    with pytest.raises(ValueError):
        Atom(
            atom_id="atm",
            memory_space_id="space",
            source=None,  # type: ignore[arg-type]
            content=_content(),
            extraction=_extraction(),
            content_digest="d",
            created_at=datetime.now(timezone.utc),
        )


def test_atom_created_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError):
        Atom(
            atom_id="atm",
            memory_space_id="space",
            source=_source(),
            content=_content(),
            extraction=_extraction(),
            content_digest="d",
            created_at=datetime(2020, 1, 1),  # noqa: DTZ001
        )


def test_atom_does_not_self_supersede() -> None:
    with pytest.raises(ValueError):
        Atom(
            atom_id="atm",
            memory_space_id="space",
            source=_source(),
            content=_content(),
            extraction=_extraction(),
            content_digest="d",
            created_at=datetime.now(timezone.utc),
            supersedes_atom_id="atm",
        )


def test_atom_can_relate_to_previous_atom() -> None:
    atom = Atom(
        atom_id="atm_new",
        memory_space_id="space",
        source=_source(),
        content=_content(),
        extraction=_extraction(),
        content_digest="d",
        created_at=datetime.now(timezone.utc),
        supersedes_atom_id="atm_old",
    )

    assert atom.supersedes_atom_id == "atm_old"
