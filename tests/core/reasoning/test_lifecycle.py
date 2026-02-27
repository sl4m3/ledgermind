import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.schemas import DecisionStream, DecisionPhase, DecisionVitality, PatternScope
from ledgermind.core.reasoning.lifecycle import LifecycleEngine

def test_temporal_drift_and_recovery():
    engine = LifecycleEngine(observation_window_days=30.0)
    now = datetime(2026, 1, 1)
    
    stream = DecisionStream(
        decision_id="test_drift_1",
        target="drift_target",
        title="Test Drift",
        rationale="Testing temporal logic",
        scope=PatternScope.SYSTEM,
        phase=DecisionPhase.EMERGENT,
        vitality=DecisionVitality.ACTIVE,
        first_seen=now - timedelta(days=10)
    )
    
    # Simulate active period
    dates_active = [now - timedelta(days=x) for x in range(10, 0, -2)]
    engine.calculate_temporal_signals(stream, dates_active, now)
    assert stream.lifetime_days >= 8.0
    assert stream.frequency == 5
    
    stream = engine.update_vitality(stream, now)
    assert stream.vitality == DecisionVitality.ACTIVE
    
    # Pause for 15 days
    later = now + timedelta(days=15)
    stream = engine.update_vitality(stream, later)
    assert stream.vitality == DecisionVitality.DECAYING
    
    # Pause for 35 days total
    even_later = now + timedelta(days=35)
    stream = engine.update_vitality(stream, even_later)
    assert stream.vitality == DecisionVitality.DORMANT
    
    # Recovery
    recovery_dates = dates_active + [even_later]
    engine.calculate_temporal_signals(stream, recovery_dates, even_later)
    stream = engine.update_vitality(stream, even_later)
    assert stream.vitality == DecisionVitality.ACTIVE

def test_burst_protection():
    engine = LifecycleEngine(observation_window_days=30.0)
    now = datetime(2026, 1, 1)
    
    stream = DecisionStream(
        decision_id="test_burst_1",
        target="burst_target",
        title="Test Burst",
        rationale="Testing burst protection",
        scope=PatternScope.LOCAL,
        phase=DecisionPhase.EMERGENT,
        vitality=DecisionVitality.ACTIVE,
        first_seen=now
    )
    
    # 100 events in 1 day
    dates_burst = [now + timedelta(hours=x) for x in range(100)]
    end_of_burst = dates_burst[-1]
    
    engine.calculate_temporal_signals(stream, dates_burst, end_of_burst)
    assert stream.frequency == 100
    assert stream.coverage < 0.2  # 4 days / 30 = 0.13
    
    stream = engine.promote_stream(stream)
    # Shouldn't become CANONICAL due to low coverage
    assert stream.phase == DecisionPhase.EMERGENT

def test_intervention_override():
    engine = LifecycleEngine(observation_window_days=30.0)
    now = datetime.now()
    
    stream = DecisionStream(
        decision_id="intervention_1",
        target="arch_target",
        title="Intervention",
        rationale="Manual override",
        provenance="internal"
    )
    
    stream = engine.process_intervention(stream, now)
    assert stream.phase == DecisionPhase.EMERGENT
    assert stream.estimated_removal_cost == 0.8
    assert stream.scope == PatternScope.SYSTEM
    
    # Even interventions decay
    future = now + timedelta(days=40)
    stream = engine.update_vitality(stream, future)
    assert stream.vitality == DecisionVitality.DORMANT

