import pytest
from ledgermind.core.core.knowledge import KnowledgeItem, Phase
from ledgermind.core.reasoning.promotion import PromotionEngine

def test_pattern_to_emergent():
    engine = PromotionEngine()
    
    # Standard path
    item = KnowledgeItem(
        fid="pattern_test_abc", title="test", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        total_evidence_count=20, coverage=0.2,
    )
    assert engine.check_promotion(item) == Phase.EMERGENT
    
    # Alternative path
    item2 = KnowledgeItem(
        fid="pattern_test2_def", title="test", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        confidence=0.5, total_evidence_count=10,
    )
    assert engine.check_promotion(item2) == Phase.EMERGENT

def test_emergent_to_canonical():
    engine = PromotionEngine()
    
    item = KnowledgeItem(
        fid="emergent_test_abc", title="test", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        total_evidence_count=50, stability_score=0.5, coverage=0.2,
        phase=Phase.EMERGENT,
    )
    assert engine.check_promotion(item) == Phase.CANONICAL

def test_no_promotion():
    engine = PromotionEngine()
    
    # Not enough evidence
    item = KnowledgeItem(
        fid="pattern_test_abc", title="test", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        total_evidence_count=5, coverage=0.1,
    )
    assert engine.check_promotion(item) is None
