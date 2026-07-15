import pytest
from datetime import datetime
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality

def test_knowledge_item_creation():
    item = KnowledgeItem(
        fid="pattern_20260713_120000_000000_abc123",
        title="Test Knowledge",
        target="core/test",
        profile="hermes",
        rationale="Test rationale",
        compressive_rationale="Test summary",
        strengths=["strength1"],
        objections=["objection1"],
        consequences=["consequence1"],
    )
    assert item.fid == "pattern_20260713_120000_000000_abc123"
    assert item.phase == Phase.PATTERN
    assert item.vitality == Vitality.ACTIVE
    assert item.confidence == 0.0
    assert item.stability_score == 0.0
    assert item.total_evidence_count == 0

def test_knowledge_item_confidence_calculation():
    item = KnowledgeItem(
        fid="pattern_test_abc",
        title="Test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        hit_count=10,
    )
    # Confidence is calculated via calculate_confidence method
    assert item.calculate_confidence() == 1.0  # Saturated at 10 hits
    
    # Verify formula works for other values
    item.hit_count = 0
    assert item.calculate_confidence() == 0.0
    
    item.hit_count = 1
    assert item.calculate_confidence() == pytest.approx(0.30, abs=0.01)
