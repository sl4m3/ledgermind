"""Contract tests for context retrieval v1."""

from __future__ import annotations

import pydantic
import pytest

from ledgermind_core.contracts.context_v1 import (
    ContextItemV1,
    RetrieveContextRequestV1,
    RetrieveContextResultV1,
)


def test_valid_retrieve_context_request() -> None:
    request = RetrieveContextRequestV1(
        api_version="1",
        memory_space_id="hermes:src_01K0ABCDEF:default",
        query="как сделать хранение атомарным",
        limit=10,
        min_phase="pattern",
    )

    assert request.api_version == "1"
    assert request.limit == 10


def test_unknown_request_field_is_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        RetrieveContextRequestV1(
            api_version="1",
            memory_space_id="space",
            query="q",
            limit=5,
            confidence=0.9,  # type: ignore[arg-type]
        )


def test_retrieve_context_limits_are_validated() -> None:
    with pytest.raises(pydantic.ValidationError):
        RetrieveContextRequestV1(
            api_version="1",
            memory_space_id="space",
            query="",
            limit=0,
        )

    with pytest.raises(pydantic.ValidationError):
        RetrieveContextRequestV1(
            api_version="1",
            memory_space_id="space",
            query="x",
            limit=51,
        )


def test_context_item_and_result_are_valid() -> None:
    item = ContextItemV1(
        knowledge_id="kn_1",
        title="t",
        target="g",
        statement="s",
        rationale="r",
        phase="pattern",
        score=0.7,
        evidence_count=2,
        source_atom_ids=["atm_1", "atm_2"],
    )

    result = RetrieveContextResultV1(api_version="1", items=[item])
    assert result.items[0].knowledge_id == "kn_1"


def test_context_score_validation() -> None:
    with pytest.raises(pydantic.ValidationError):
        ContextItemV1(
            knowledge_id="kn_1",
            title="t",
            target="g",
            statement="s",
            rationale="r",
            phase="pattern",
            score=1.2,
            evidence_count=2,
            source_atom_ids=["atm_1"],
        )
