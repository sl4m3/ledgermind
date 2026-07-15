import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality
from ledgermind.core.reasoning.decay import NewDecayEngine

def test_decay_rate_calculation():
    engine = NewDecayEngine()
    
    # Fast decay (confidence < 0.3)
    assert engine.get_decay_rate(0.2) == 0.15
    
    # Medium decay (confidence 0.3-0.7)
    assert engine.get_decay_rate(0.5) == 0.05
    
    # Slow decay (confidence > 0.7)
    assert engine.get_decay_rate(0.8) == 0.01

def test_decay_application():
    engine = NewDecayEngine()
    item = KnowledgeItem(
        fid="pattern_test_abc",
        title="test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        confidence=0.8,
        total_evidence_count=10,  # Enough evidence to pass minimum retention
        first_seen=datetime.now() - timedelta(days=30),  # Old enough to pass minimum retention
        last_seen=datetime.now() - timedelta(days=14),
    )
    
    new_confidence = engine.apply_decay(item)
    assert new_confidence < 0.8

def test_vitality_transitions():
    engine = NewDecayEngine()
    
    # ACTIVE -> DECAYING
    item = KnowledgeItem(
        fid="pattern_test_abc",
        title="test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        confidence=0.5,
        last_hit_at=datetime.now() - timedelta(days=40),
    )
    assert engine.calculate_vitality(item) == Vitality.DECAYING
    
    # DECAYING -> ACTIVE
    item.last_hit_at = datetime.now() - timedelta(days=5)
    assert engine.calculate_vitality(item) == Vitality.ACTIVE

def test_superseded_items_skipped():
    engine = NewDecayEngine()
    item = KnowledgeItem(
        fid="pattern_test_abc",
        title="test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        confidence=0.8,
        superseded_by="pattern_other_abc",
    )
    
    # Should return same confidence (not decayed)
    new_confidence = engine.apply_decay(item)
    assert new_confidence == 0.8
    
    # Should return same vitality (not changed)
    vitality = engine.calculate_vitality(item)
    assert vitality == Vitality.ACTIVE
