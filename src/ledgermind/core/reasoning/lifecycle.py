import logging
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from ledgermind.core.core.schemas import (
    DecisionStream, DecisionPhase, DecisionVitality, PatternScope
)

# Optional observability
try:
    from ledgermind.server.metrics import PHASE_TRANSITIONS, STREAM_PROMOTIONS
except ImportError:
    PHASE_TRANSITIONS = None
    STREAM_PROMOTIONS = None

logger = logging.getLogger(__name__)

class LifecycleEngine:
    def __init__(self, observation_window_days: float = 30.0):
        self.observation_window_days = observation_window_days

    def calculate_temporal_signals(
        self, 
        stream: DecisionStream, 
        reinforcement_dates: List[datetime], 
        now: datetime
    ) -> DecisionStream:
        """
        Updates temporal metrics: reinforcement_density, stability, coverage, lifetime_days.
        """
        if not reinforcement_dates:
            stream.lifetime_days = (now - stream.first_seen).total_seconds() / 86400.0
            stream.reinforcement_density = 0.0
            stream.stability_score = 0.0
            stream.coverage = stream.lifetime_days / self.observation_window_days
            return stream

        sorted_dates = sorted(reinforcement_dates)
        if stream.first_seen > sorted_dates[0]:
            stream.first_seen = sorted_dates[0]
            
        stream.last_seen = sorted_dates[-1]
        
        lifetime_secs = (stream.last_seen - stream.first_seen).total_seconds()
        stream.lifetime_days = lifetime_secs / 86400.0
        
        # Avoid division by zero
        safe_lifetime = max(stream.lifetime_days, 0.01)
        
        stream.frequency = len(sorted_dates)
        stream.reinforcement_density = stream.frequency / safe_lifetime
        
        stream.coverage = stream.lifetime_days / self.observation_window_days

        if len(sorted_dates) > 2:
            intervals = [(sorted_dates[i] - sorted_dates[i-1]).total_seconds() / 86400.0 
                         for i in range(1, len(sorted_dates))]
            if len(intervals) > 1:
                var = statistics.variance(intervals)
                # Lower variance = higher stability. Use an inverse function or normalize.
                # Assuming variance of 0 is perfect stability (score 1.0).
                stream.stability_score = max(0.0, 1.0 - (var / (safe_lifetime + 1.0)))
            else:
                stream.stability_score = 0.0
        elif len(sorted_dates) == 2:
            stream.stability_score = 0.3 # Moderate stability signal for 2 events
        else:
            stream.stability_score = 0.0

        return stream

    def estimate_removal_cost(self, stream: DecisionStream) -> float:
        """
        Deterministic calculation of removal cost based on scope and evidence.
        """
        score = 0.0
        if stream.scope == PatternScope.INFRA:
            score += 0.5
        elif stream.scope == PatternScope.SYSTEM:
            score += 0.3
            
        # Add cost based on how many things it affects (heuristics)
        score += min(len(stream.consequences) * 0.05, 0.2)
        score += min(stream.unique_contexts * 0.05, 0.3)
        
        if getattr(stream, 'provenance', 'internal') == 'external':
            score += 0.4
            
        # Add real-usage signals
        score += min(stream.hit_count / 100.0, 0.2)  # Boost for real use
        score += stream.confidence * 0.1  # High confidence = harder to delete
            
        return min(score, 1.0)

    def estimate_utility(self, stream: DecisionStream) -> float:
        """
        Deterministic calculation of utility based on frequency and success signals.
        """
        score = 0.0
        score += min(stream.frequency / 10.0, 0.4)
        score += min(stream.unique_contexts / 5.0, 0.3)
        
        if stream.scope in [PatternScope.SYSTEM, PatternScope.INFRA]:
            score += 0.2
            
        return min(score, 1.0)

    def update_vitality(self, stream: DecisionStream, now: datetime) -> DecisionStream:
        """
        Updates the vitality state: ACTIVE -> DECAYING -> DORMANT.
        """
        days_since_last = (now - stream.last_seen).total_seconds() / 86400.0
        
        if days_since_last < 7.0:
            stream.vitality = DecisionVitality.ACTIVE
        elif days_since_last < 30.0:
            stream.vitality = DecisionVitality.DECAYING
            # Decay confidence slightly
            stream.confidence = max(0.0, stream.confidence - 0.05)
        else:
            stream.vitality = DecisionVitality.DORMANT
            stream.confidence = max(0.0, stream.confidence - 0.2)
            
        return stream

    def promote_stream(self, stream: DecisionStream) -> DecisionStream:
        """
        Evaluates and transitions Phase based on temporal signals and cost.
        PATTERN -> EMERGENT -> CANONICAL
        """
        old_phase = stream.phase
        
        # Re-calculate static properties
        stream.estimated_removal_cost = self.estimate_removal_cost(stream)
        stream.estimated_utility = self.estimate_utility(stream)
        
        # Calculate combined confidence with momentum (Issue #6)
        # Increased weights for utility and stability to allow faster growth for successful patterns
        calculated_conf = 0.4 * stream.estimated_utility + 0.3 * stream.estimated_removal_cost + 0.3 * stream.stability_score
        momentum = 0.5 # Increased from 0.3 for faster adaptation
        stream.confidence = stream.confidence * (1.0 - momentum) + calculated_conf * momentum
        
        if stream.phase == DecisionPhase.PATTERN:
            # Transition to EMERGENT requires some minimum evidence or confidence
            if stream.frequency >= 3 or stream.estimated_removal_cost >= 0.4 or stream.confidence >= 0.5:
                # Interventions skip strict lifetime checks typically
                # For patterns, we allow earlier crystallization if the signal is strong
                if stream.lifetime_days > 0.5 or stream.frequency >= 5 or getattr(stream, 'provenance', 'internal') == 'external' or stream.estimated_removal_cost >= 0.5:
                    stream.phase = DecisionPhase.EMERGENT
                    
        elif stream.phase == DecisionPhase.EMERGENT:
            # Transition to CANONICAL is very strict to prevent burst-crystallization
            # Requires good coverage, high stability, high cost, and good frequency
            if (stream.coverage > 0.3 and 
                stream.stability_score > 0.6 and 
                stream.estimated_removal_cost > 0.5 and
                stream.vitality == DecisionVitality.ACTIVE):
                stream.phase = DecisionPhase.CANONICAL
                
        # Observe metrics
        if stream.phase != old_phase:
            if PHASE_TRANSITIONS:
                PHASE_TRANSITIONS.labels(from_phase=old_phase.value, to_phase=stream.phase.value).inc()
            if STREAM_PROMOTIONS:
                STREAM_PROMOTIONS.labels(target_phase=stream.phase.value).inc()

        return stream

    def process_intervention(self, stream: DecisionStream, now: datetime) -> DecisionStream:
        """
        Special path for manual KIND_INTERVENTION events.
        They get high initial cost and skip direct to EMERGENT usually, but are still subject to vitality decay.
        """
        stream.scope = PatternScope.SYSTEM
        stream.first_seen = now
        stream.last_seen = now
        stream.estimated_removal_cost = 0.8
        stream.estimated_utility = 0.5
        stream.phase = DecisionPhase.EMERGENT
        stream.vitality = DecisionVitality.ACTIVE
        stream.confidence = 0.7
        return stream

    def detect_behavioral_patterns(self, clusters: Dict[str, Dict[str, Any]]) -> List[DecisionStream]:
        """
        Transforms evidence clusters into base PATTERN streams.
        To be called by ReflectionEngine.
        """
        streams = []
        for target, stats in clusters.items():
            import uuid
            stream = DecisionStream(
                decision_id=str(uuid.uuid4()),
                target=target,
                title=f"Behavioral pattern in {target}",
                rationale=f"Observed repeated events related to {target}",
                phase=DecisionPhase.PATTERN,
                vitality=DecisionVitality.ACTIVE,
                evidence_event_ids=stats.get('all_ids', []),
                frequency=len(stats.get('all_ids', [])),
                unique_contexts=stats.get('commits', 0) + 1  # approximation
            )
            streams.append(stream)
        return streams
