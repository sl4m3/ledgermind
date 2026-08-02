"""Tests for atom content and extraction metadata."""

import pytest

from domain.atom import AtomContent, ExtractionInfo


def test_atom_content_validates_required_strings() -> None:
    content = AtomContent(
        title=" t ",
        target="target",
        statement="fact",
        rationale="",
        result="",
        artifacts=["a", "b"],
    )

    assert content.artifacts == ("a", "b")


def test_atom_content_rejects_empty_fields() -> None:
    invalid_payloads = [
        {"title": "", "target": "target", "statement": "statement", "rationale": "", "result": ""},
        {"title": "title", "target": "", "statement": "statement", "rationale": "", "result": ""},
        {"title": "title", "target": "target", "statement": "   ", "rationale": "", "result": ""},
    ]

    for payload in invalid_payloads:
        with pytest.raises(ValueError):
            AtomContent(artifacts=(), **payload)


def test_atom_content_length_limits() -> None:
    AtomContent(
        title="a" * 240,
        target="b" * 240,
        statement="c",
        rationale="",
        result="",
    )

    with pytest.raises(ValueError):
        AtomContent(
            title="a" * 241,
            target="target",
            statement="s",
            rationale="",
            result="",
        )

    with pytest.raises(ValueError):
        AtomContent(
            title="title",
            target="b" * 241,
            statement="s",
            rationale="",
            result="",
        )


def test_extraction_info_validation() -> None:
    ExtractionInfo(
        host="local-host",
        provider="",
        model="",
        prompt_version=1,
        schema_version=1,
        purpose="ledgermind.atom.extract",
    )

    with pytest.raises(ValueError):
        ExtractionInfo(
            host="",
            provider="",
            model="",
            prompt_version=0,
            schema_version=1,
            purpose="x",
        )
