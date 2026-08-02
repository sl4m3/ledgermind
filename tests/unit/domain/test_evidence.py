"""Tests for evidence entities."""

from datetime import datetime, timezone

import pytest

from ledgermind_core.domain.evidence import (
    EvidenceRelation,
    KnowledgeEvidence,
    assert_has_origin_relation,
)


def test_evidence_relation_has_required_values() -> None:
    assert EvidenceRelation.ORIGIN.value == "origin"
    assert EvidenceRelation.SUPPORTS.value == "supports"
    assert EvidenceRelation.CONTRADICTS.value == "contradicts"
    assert EvidenceRelation.REFINES.value == "refines"


def test_knowledge_evidence_is_immutable_and_validates() -> None:
    evidence = KnowledgeEvidence(
        knowledge_id="kn_1",
        atom_id="at_1",
        relation=EvidenceRelation.ORIGIN,
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert evidence.relation == EvidenceRelation.ORIGIN

    with pytest.raises(ValueError):
        KnowledgeEvidence(
            knowledge_id="",
            atom_id="at_1",
            relation=EvidenceRelation.ORIGIN,
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

    with pytest.raises(ValueError):
        KnowledgeEvidence(
            knowledge_id="kn_1",
            atom_id="at_1",
            relation=EvidenceRelation.ORIGIN,
            created_at=datetime(2020, 1, 1),  # noqa: DTZ001
        )


def test_knowledge_creation_requires_origin_evidence() -> None:
    evidences = [
        KnowledgeEvidence(
            knowledge_id="kn_1",
            atom_id="at_1",
            relation=EvidenceRelation.SUPPORTS,
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        ),
    ]

    with pytest.raises(ValueError):
        assert_has_origin_relation(evidences)

    evidences.append(
        KnowledgeEvidence(
            knowledge_id="kn_1",
            atom_id="at_2",
            relation=EvidenceRelation.ORIGIN,
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
    )

    assert_has_origin_relation(evidences)
