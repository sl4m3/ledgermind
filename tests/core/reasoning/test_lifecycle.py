import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.schemas import DecisionStream, DecisionPhase, DecisionVitality
from ledgermind.core.reasoning.lifecycle import LifecycleEngine

def test_temporal_drift_and_recovery():
    engine = LifecycleEngine(observation_window_days=30.0)
    now = datetime(2026, 1, 1)

    stream = DecisionStream(
        decision_id="test_drift_1",
        target="drift_target",
        title="Test Drift",
        rationale="Testing temporal logic",
        phase=DecisionPhase.EMERGENT,
        vitality=DecisionVitality.ACTIVE,
        first_seen=now - timedelta(days=10),
        last_hit_at=now,  # Set last hit to avoid immediate decay
        total_evidence_count=5  # V7.0: use total_evidence_count instead of frequency
    )

    # 1. Simulate active period
    dates_active = [now - timedelta(days=x) for x in range(10, 0, -2)]
    stream = engine.calculate_temporal_signals(stream, dates_active, now)
    assert stream.lifetime_days >= 8.0
    # V7.0: total_evidence_count increments by number of reinforcement dates (5)
    assert stream.total_evidence_count == 10  # 5 initial + 5 new
    assert stream.vitality == DecisionVitality.ACTIVE

    # 2. Simulate Decay: Pause for 35 days (exceeds 30 day window)
    later = now + timedelta(days=35)
    # We simulate a search hit that was long ago
    stream = stream.model_copy(update={"last_hit_at": now})
    stream = engine.calculate_temporal_signals(stream, [], later)
    assert stream.vitality == DecisionVitality.DECAYING

    # 3. Recovery: Recent hit triggers reactivation
    recent_hit = later - timedelta(hours=1)
    stream = stream.model_copy(update={"last_hit_at": recent_hit})
    stream = engine.calculate_temporal_signals(stream, [later], later)
    assert stream.vitality == DecisionVitality.ACTIVE

def test_burst_protection():
    engine = LifecycleEngine(observation_window_days=30.0)
    now = datetime(2026, 1, 1)

    stream = DecisionStream(
        decision_id="test_burst_1",
        target="burst_target",
        title="Test Burst",
        rationale="Testing burst protection",
        phase=DecisionPhase.EMERGENT,
        vitality=DecisionVitality.ACTIVE,
        first_seen=now,
        last_hit_at=now,
        total_evidence_count=100  # V7.0: use total_evidence_count
    )

    # 100 events in 1 day
    dates_burst = [now + timedelta(hours=x) for x in range(100)]
    end_of_burst = dates_burst[-1]

    stream = engine.calculate_temporal_signals(stream, dates_burst, end_of_burst)
    # V7.0: total_evidence_count increments by number of reinforcement dates (100)
    assert stream.total_evidence_count == 200  # 100 initial + 100 new
    # V7.0: coverage is now lifetime_days / observation_window_days
    # lifetime_days is calculated from first_seen to now, so coverage can be > 1
    assert stream.lifetime_days > 0  # Ensure lifetime is calculated

    stream = engine.promote_stream(stream)
    # Shouldn't become CANONICAL due to low coverage despite high evidence
    assert stream.phase == DecisionPhase.EMERGENT

def test_intervention_override():
    engine = LifecycleEngine(observation_window_days=30.0)
    now = datetime.now()

    stream = DecisionStream(
        decision_id="intervention_1",
        target="arch_target",
        title="Intervention",
        rationale="Manual override"
        # V7.0: provenance removed
    )

    stream = engine.process_intervention(stream, now)
    # Interventions are EMERGENT in our current system (to be confirmed by time)
    assert stream.phase == DecisionPhase.EMERGENT
    assert stream.stability_score == 0.95

    # Test decay for interventions too
    future = now + timedelta(days=40)
    # Simulate that nobody searched for this intervention for 40 days
    stream = stream.model_copy(update={"last_hit_at": now})
    stream = engine.calculate_temporal_signals(stream, [], future)
    assert stream.vitality == DecisionVitality.DECAYING
