import pytest
from datetime import datetime, timedelta
from ledgermind.core.reasoning.lifecycle import LifecycleEngine
from ledgermind.core.core.schemas import DecisionStream, DecisionVitality

@pytest.fixture
def engine():
    return LifecycleEngine(observation_window_days=30.0)

def test_utility_based_decay(engine):
    """Verify that vitality downgrades to DECAYING if last_hit_at is old."""
    # Round to ms for consistency with core
    now = datetime.now().replace(microsecond=(datetime.now().microsecond // 1000) * 1000)
    # 31 days ago
    old_hit = now - timedelta(days=31)
    
    stream = DecisionStream(
        decision_id="test-1",
        target="area",
        title="Test",
        rationale="Long enough rationale for validation",
        vitality=DecisionVitality.ACTIVE,
        last_hit_at=old_hit
    )
    
    # Run temporal calculation
    updated = engine.calculate_temporal_signals(stream, [], now)
    
    assert updated.vitality == DecisionVitality.DECAYING

def test_vitality_reactivation(engine):
    """Verify that a DECAYING stream returns to ACTIVE if hit recently."""
    now = datetime.now().replace(microsecond=(datetime.now().microsecond // 1000) * 1000)
    # Hit just now
    recent_hit = now - timedelta(hours=1)
    
    stream = DecisionStream(
        decision_id="test-2",
        target="area",
        title="Test",
        rationale="Long enough rationale for validation",
        vitality=DecisionVitality.DECAYING,
        last_hit_at=recent_hit
    )
    
    updated = engine.calculate_temporal_signals(stream, [], now)
    
    assert updated.vitality == DecisionVitality.ACTIVE

def test_stability_score_increment(engine):
    """Verify that stability_score grows when knowledge is reinforced."""
    now = datetime.now()
    stream = DecisionStream(
        decision_id="test-3",
        target="area",
        title="Test",
        rationale="Long enough rationale for validation",
        stability_score=0.0,
        frequency=0
    )
    
    # Reinforce with 2 new dates
    reinforcement = [now - timedelta(days=1), now]
    updated = engine.calculate_temporal_signals(stream, reinforcement, now)
    
    # Should be > 0.0
    assert updated.stability_score > 0.0
    assert updated.stability_score <= 1.0
