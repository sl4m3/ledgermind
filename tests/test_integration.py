import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality
from ledgermind.core.reasoning.pipeline import LifecyclePipeline

def test_full_pipeline():
    pipeline = LifecyclePipeline()
    
    # Create test knowledge items
    items = [
        KnowledgeItem(
            fid=f"pattern_item_{i}_abc",
            title=f"Knowledge {i}",
            target=f"target/{i}",
            profile="hermes",
            rationale=f"Rationale {i}",
            compressive_rationale=f"Summary {i}",
            strengths=[],
            objections=[],
            consequences=[],
            confidence=i * 0.1,
            total_evidence_count=i * 5,
        )
        for i in range(10)
    ]
    
    result = pipeline.run(items)
    
    assert result.merge_count >= 0
    assert result.decay_count >= 0
    assert result.promote_count >= 0

def test_phase_transitions():
    from ledgermind.core.reasoning.promotion import PromotionEngine
    
    engine = PromotionEngine()
    
    # PATTERN -> EMERGENT
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
        total_evidence_count=20,
        coverage=0.2,
    )
    assert engine.check_promotion(item) == Phase.EMERGENT
    
    # EMERGENT -> CANONICAL
    item2 = KnowledgeItem(
        fid="emergent_test_def",
        title="Test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        total_evidence_count=50,
        stability_score=0.5,
        coverage=0.2,
        phase=Phase.EMERGENT,
    )
    assert engine.check_promotion(item2) == Phase.CANONICAL
