"""Property-based tests for LedgerMind core domain invariants."""

from __future__ import annotations

from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import assume, given

from domain import AtomContent, EvidenceRelation, ExtractionInfo, KnowledgeEvidence
from domain.knowledge import KnowledgeItem
from domain.phase import Phase


@given(
    title=st.text(min_size=1, max_size=240).map(str.strip),
    target=st.text(min_size=1, max_size=240).map(str.strip),
    statement=st.text(min_size=1).map(str.strip),
    rationale=st.text(min_size=1).map(str.strip),
    result=st.text(min_size=1).map(str.strip),
    artifacts=st.lists(st.text(min_size=1), max_size=5),
)
def test_atom_content_valid_input_preserves_fields(
    title: str,
    target: str,
    statement: str,
    rationale: str,
    result: str,
    artifacts: list[str],
) -> None:
    assume(title)
    assume(target)
    assume(statement)
    assume(rationale)
    assume(result)
    atom = AtomContent(
        title=title,
        target=target,
        statement=statement,
        rationale=rationale,
        result=result,
        artifacts=tuple(artifacts),
    )
    assert atom.title == title
    assert atom.target == target
    assert atom.statement == statement
    assert atom.rationale == rationale
    assert atom.result == result
    assert atom.artifacts == tuple(artifacts)


@given(
    title=st.text(min_size=241),
)
def test_atom_content_rejects_title_over_240_chars(title: str) -> None:
    try:
        AtomContent(
            title=title,
            target="target",
            statement="statement",
            rationale="rationale",
            result="result",
        )
    except ValueError as exc:
        assert "title is too long" in str(exc)
    else:
        raise AssertionError("expected ValueError for title > 240")


@given(
    host=st.text(min_size=1),
    provider=st.text(min_size=0),
    model=st.text(min_size=0),
    prompt_version=st.integers(min_value=1, max_value=999),
    schema_version=st.integers(min_value=1, max_value=999),
    purpose=st.text(min_size=1),
)
def test_extraction_info_round_trip_preserves_fields(
    host: str,
    provider: str,
    model: str,
    prompt_version: int,
    schema_version: int,
    purpose: str,
) -> None:
    info = ExtractionInfo(
        host=host,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        purpose=purpose,
    )
    assert info.host == host
    assert info.provider == provider
    assert info.model == model
    assert info.prompt_version == prompt_version
    assert info.schema_version == schema_version
    assert info.purpose == purpose


@given(
    knowledge_id=st.text(min_size=1),
    memory_space_id=st.text(min_size=1),
    title=st.text(min_size=1),
    target=st.text(min_size=1),
    statement=st.text(min_size=1),
    rationale=st.text(min_size=1),
    version=st.integers(min_value=1, max_value=999),
)
def test_knowledge_item_is_current_when_not_superseded_nor_deleted(
    knowledge_id: str,
    memory_space_id: str,
    title: str,
    target: str,
    statement: str,
    rationale: str,
    version: int,
) -> None:
    now = datetime.now(timezone.utc)
    item = KnowledgeItem(
        knowledge_id=knowledge_id,
        memory_space_id=memory_space_id,
        title=title,
        target=target,
        statement=statement,
        rationale=rationale,
        phase=Phase.PATTERN,
        version=version,
        created_at=now,
        updated_at=now,
    )
    assert item.is_current is True


@given(
    knowledge_id=st.text(min_size=1),
    memory_space_id=st.text(min_size=1),
    version=st.integers(min_value=1, max_value=999),
)
def test_knowledge_item_is_not_current_when_deleted(
    knowledge_id: str,
    memory_space_id: str,
    version: int,
) -> None:
    now = datetime.now(timezone.utc)
    deleted = datetime.now(timezone.utc)
    item = KnowledgeItem(
        knowledge_id=knowledge_id,
        memory_space_id=memory_space_id,
        title="title",
        target="target",
        statement="statement",
        rationale="rationale",
        phase=Phase.PATTERN,
        version=version,
        created_at=now,
        updated_at=now,
        deleted_at=deleted,
    )
    assert item.is_current is False


@given(
    knowledge_id=st.text(min_size=1),
    memory_space_id=st.text(min_size=1),
    version=st.integers(min_value=1, max_value=999),
)
def test_knowledge_item_rejects_self_supersede(
    knowledge_id: str,
    memory_space_id: str,
    version: int,
) -> None:
    now = datetime.now(timezone.utc)
    try:
        KnowledgeItem(
            knowledge_id=knowledge_id,
            memory_space_id=memory_space_id,
            title="title",
            target="target",
            statement="statement",
            rationale="rationale",
            phase=Phase.PATTERN,
            version=version,
            created_at=now,
            updated_at=now,
            superseded_by_id=knowledge_id,
        )
    except ValueError as exc:
        assert "knowledge cannot supersede itself" in str(exc)
    else:
        raise AssertionError("expected ValueError for self-supersede")


@given(
    knowledge_id=st.text(min_size=1),
    memory_space_id=st.text(min_size=1),
    version=st.integers(min_value=1, max_value=999),
    seconds_offset=st.integers(min_value=1, max_value=3600),
)
def test_knowledge_item_rejects_updated_at_before_created_at(
    knowledge_id: str,
    memory_space_id: str,
    version: int,
    seconds_offset: int,
) -> None:
    created = datetime.now(timezone.utc)
    updated = datetime.fromtimestamp(created.timestamp() - seconds_offset, tz=timezone.utc)
    try:
        KnowledgeItem(
            knowledge_id=knowledge_id,
            memory_space_id=memory_space_id,
            title="title",
            target="target",
            statement="statement",
            rationale="rationale",
            phase=Phase.PATTERN,
            version=version,
            created_at=created,
            updated_at=updated,
        )
    except ValueError as exc:
        assert "updated_at must be >= created_at" in str(exc)
    else:
        raise AssertionError("expected ValueError for updated_at < created_at")


def test_knowledge_evidence_all_relations_accepted() -> None:
    for relation in EvidenceRelation:
        evidence = KnowledgeEvidence(
            knowledge_id="k1",
            atom_id="a1",
            relation=relation,
            created_at=datetime.now(timezone.utc),
        )
        assert evidence.relation is relation


@given(
    knowledge_id=st.text(min_size=1),
    atom_id=st.text(min_size=1),
)
def test_knowledge_evidence_round_trip_preserves_ids(
    knowledge_id: str,
    atom_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    evidence = KnowledgeEvidence(
        knowledge_id=knowledge_id,
        atom_id=atom_id,
        relation=EvidenceRelation.ORIGIN,
        created_at=now,
    )
    assert evidence.knowledge_id == knowledge_id
    assert evidence.atom_id == atom_id
    assert evidence.created_at == now
