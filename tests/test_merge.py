import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality
from ledgermind.core.reasoning.merge import MergeEngine

def test_similarity_scoring():
    engine = MergeEngine()
    
    # Same target, same phase, same profile
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="ui/hero", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN,
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="ui/hero", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN,
    )
    similarity = engine.calculate_similarity(candidate, target)
    assert similarity > 0.6  # Same target, same phase

def test_profile_gate():
    engine = MergeEngine()
    
    # Different profiles → SKIP
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN,
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="t", profile="openclaw", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN,
    )
    assert engine.should_merge(candidate, target) == False

def test_session_boost():
    engine = MergeEngine()
    
    # Same session + high similarity → boost
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="ui/hero", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, session_id="session_123",
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="ui/hero", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, session_id="session_123",
    )
    similarity = engine.calculate_similarity(candidate, target)
    # Should have session boost because similarity > 0.6
    assert similarity > 0.8

def test_quality_assessment():
    engine = MergeEngine()
    
    item = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        confidence=0.7, stability_score=0.5, total_evidence_count=5,
        first_seen=datetime.now() - timedelta(days=15),
    )
    quality = engine.assess_quality(item)
    assert 0.3 < quality < 0.8  # Reasonable quality

def test_merge_decision_pattern():
    engine = MergeEngine()
    
    # PATTERN: easy merge (threshold 0.5)
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.3, stability_score=0.0,
        first_seen=datetime.now(),
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.4, stability_score=0.0,
        first_seen=datetime.now(),
    )
    assert engine.should_merge(candidate, target) == True

def test_merge_decision_canonical():
    engine = MergeEngine()
    
    # CANONICAL: hard merge (threshold 0.7)
    candidate = KnowledgeItem(
        fid="canonical_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.CANONICAL, confidence=0.6, stability_score=0.5,
        first_seen=datetime.now() - timedelta(days=30),
    )
    target = KnowledgeItem(
        fid="canonical_B_def", title="B", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.CANONICAL, confidence=0.7, stability_score=0.6,
        first_seen=datetime.now() - timedelta(days=30),
    )
    assert engine.should_merge(candidate, target) == True

def test_merge_dormant_revival():
    engine = MergeEngine()
    
    # DORMANT: revive through merge (threshold 0.5)
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.3, vitality=Vitality.ACTIVE,
        first_seen=datetime.now(),
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.2, vitality=Vitality.DORMANT,
        first_seen=datetime.now(),
    )
    assert engine.should_merge(candidate, target) == True

def test_supersede_with_phase_inheritance():
    engine = MergeEngine()
    
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.7,
    )
    target = KnowledgeItem(
        fid="emergent_B_def", title="B", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.EMERGENT, confidence=0.5,
    )
    
    stronger, weaker = engine.choose_stronger(candidate, target)
    engine.execute_supersede(stronger, weaker)
    
    # Phase should be inherited from stronger (EMERGENT)
    assert stronger.phase == Phase.EMERGENT
    assert weaker.superseded_by == "pattern_A_abc"
    assert stronger.total_evidence_count == 1  # 0 + 0 + 1
