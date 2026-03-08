import logging
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from ledgermind.core.utils.datetime_utils import to_naive_utc

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
        Updates temporal metrics incrementally. Handles vitality decay even if no new dates are provided.
        """
        from ledgermind.core.utils.datetime_utils import to_naive_utc
        from datetime import datetime

        # 0. Normalization and Preparation
        now_naive = to_naive_utc(now)
        reinforcement_dates = [to_naive_utc(d) for d in reinforcement_dates if d]
        
        # Accumulate updates for model_copy
        model_updates = {}

        # 1. Automatic Decay (Vitality check based on usage)
        # MUST run even if reinforcement_dates is empty
        last_hit_at = getattr(stream, 'last_hit_at', None)
        if last_hit_at:
            if isinstance(last_hit_at, str):
                try: last_hit_at = datetime.fromisoformat(last_hit_at)
                except ValueError: last_hit_at = None
            
            if last_hit_at:
                last_hit_naive = to_naive_utc(last_hit_at)
                days_since_hit = (now_naive - last_hit_naive).total_seconds() / 86400.0
                
                current_vit = getattr(stream, 'vitality', DecisionVitality.ACTIVE)
                if days_since_hit > 30.0:
                    if current_vit == DecisionVitality.ACTIVE or str(current_vit) == "active":
                        logger.info(f"Stream {stream.decision_id} is DECAYING due to inactivity ({days_since_hit:.1f} days)")
                        model_updates['vitality'] = DecisionVitality.DECAYING
                elif days_since_hit < 7.0:
                    if current_vit == DecisionVitality.DECAYING or str(current_vit) == "decaying":
                        # Re-activate if used recently
                        model_updates['vitality'] = DecisionVitality.ACTIVE

        # 2. Early Exit check (Still apply vitality updates if any)
        if not reinforcement_dates:
            # Update basic lifetime metrics if stream has history
            if stream.first_seen:
                fs_naive = to_naive_utc(stream.first_seen)
                model_updates['lifetime_days'] = (now_naive - fs_naive).total_seconds() / 86400.0
                model_updates['coverage'] = model_updates['lifetime_days'] / self.observation_window_days
            
            if model_updates:
                return stream.model_copy(update=model_updates) if hasattr(stream, "model_copy") else stream
            return stream

        # 3. Full Temporal Metrics Calculation (since we have new dates)
        sorted_dates = sorted(reinforcement_dates)
        
        # Determine boundaries
        first_seen = to_naive_utc(stream.first_seen) if stream.first_seen else sorted_dates[0]
        last_seen = to_naive_utc(stream.last_seen) if stream.last_seen else sorted_dates[-1]
        
        if stream.frequency == 0:
            first_seen, last_seen = sorted_dates[0], sorted_dates[-1]
        else:
            first_seen = min(first_seen, sorted_dates[0])
            last_seen = max(last_seen, sorted_dates[-1])
        
        model_updates['first_seen'] = first_seen
        model_updates['last_seen'] = last_seen
        
        lifetime_days = (last_seen - first_seen).total_seconds() / 86400.0
        model_updates['lifetime_days'] = lifetime_days
        safe_lifetime = max(lifetime_days, 0.01)

        # Update Frequency
        old_freq = stream.frequency
        delta_freq = len(sorted_dates)
        new_freq = old_freq + delta_freq
        model_updates['frequency'] = new_freq

        # Update Density and Coverage
        model_updates['reinforcement_density'] = new_freq / safe_lifetime
        model_updates['coverage'] = lifetime_days / self.observation_window_days

        # 4. Update Stability Score
        delta_stability = 0.0
        if delta_freq > 2:
            intervals = [(sorted_dates[i] - sorted_dates[i-1]).total_seconds() / 86400.0 
                         for i in range(1, len(sorted_dates))]
            if len(intervals) > 1:
                var = statistics.variance(intervals)
                delta_stability = max(0.0, 1.0 - (var / (safe_lifetime + 1.0)))
        elif delta_freq == 2:
            delta_stability = 0.3
        
        new_stability = stream.stability_score
        if old_freq > 0:
            new_stability = (stream.stability_score * old_freq + delta_stability * delta_freq) / new_freq
        else:
            new_stability = delta_stability
        model_updates['stability_score'] = new_stability

        # 5. Commit all updates
        if hasattr(stream, "model_copy"):
            return stream.model_copy(update=model_updates)
        else:
            for k, v in model_updates.items(): setattr(stream, k, v)
            return stream

    def estimate_removal_cost(self, stream: DecisionStream) -> float:
        """
        Deterministic calculation of removal cost based on scope and evidence.
        """
        score = 0.0
        if stream.scope == PatternScope.INFRA:
            score += 50.0
        elif stream.scope == PatternScope.SYSTEM:
            score += 20.0
        else:
            score += 5.0
            
        score += stream.frequency * 2.0
        score += stream.unique_contexts * 5.0
        return score

    def estimate_utility(self, stream: DecisionStream) -> float:
        """
        Calculates knowledge utility based on usage and stability.
        """
        base = stream.stability_score * 10.0
        usage_bonus = stream.hit_count * 0.5
        recency_penalty = 0.0
        
        # Penalyze if not seen for window/2
        if stream.last_seen:
            from datetime import datetime
            days_ago = (datetime.now() - to_naive_utc(stream.last_seen)).total_seconds() / 86400.0
            if days_ago > (self.observation_window_days / 2):
                recency_penalty = (days_ago / self.observation_window_days) * 5.0
                
        return max(0.0, base + usage_bonus - recency_penalty)

    def promote_stream(self, stream: DecisionStream) -> DecisionStream:
        """
        Analyzes metrics and decides if a stream should be promoted to a higher phase.
        """
        # 1. Pattern -> Emergent
        if stream.phase == DecisionPhase.PATTERN:
            if stream.frequency >= 5 and stream.coverage >= 0.2:
                logger.info(f"Promoting stream {stream.decision_id} to EMERGENT")
                if PHASE_TRANSITIONS: PHASE_TRANSITIONS.labels("pattern", "emergent").inc()
                return stream.model_copy(update={"phase": DecisionPhase.EMERGENT})

        # 2. Emergent -> Canonical
        if stream.phase == DecisionPhase.EMERGENT:
            if stream.frequency >= 15 and stream.stability_score >= 0.7 and stream.coverage >= 0.3:
                logger.info(f"Promoting stream {stream.decision_id} to CANONICAL")
                if PHASE_TRANSITIONS: PHASE_TRANSITIONS.labels("emergent", "canonical").inc()
                return stream.model_copy(update={"phase": DecisionPhase.CANONICAL})

        return stream

    def process_intervention(self, stream: DecisionStream, now: datetime) -> DecisionStream:
        """
        Handles manual architectural interventions.
        Interventions bypass gradual growth and force high stability.
        """
        updates = {
            "phase": DecisionPhase.EMERGENT,
            "vitality": DecisionVitality.ACTIVE,
            "stability_score": 0.95,
            "estimated_removal_cost": 1.0,
            "last_seen": to_naive_utc(now),
            "frequency": stream.frequency + 1
        }
        if STREAM_PROMOTIONS: STREAM_PROMOTIONS.labels("intervention").inc()
        return stream.model_copy(update=updates)
