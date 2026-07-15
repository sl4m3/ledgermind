from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
import math
from ledgermind.core.utils.datetime_utils import to_naive_utc
from ledgermind.core.core.knowledge import KnowledgeItem, Vitality, Phase

class DecayReport:
    """
    Summary of the results from a memory decay process.
    """
    def __init__(self, archived: int, pruned: int, retained: int, semantic_forgotten: int = 0):
        self.archived = archived
        self.pruned = pruned
        self.retained_by_link = retained
        self.semantic_forgotten = semantic_forgotten

    def __repr__(self):
        return f"<DecayReport archived={self.archived}, pruned={self.pruned}, semantic_forgotten={self.semantic_forgotten}>"

class NewDecayEngine:
    """Confidence-based decay engine for KnowledgeItems."""
    
    def __init__(
        self,
        fast_threshold: float = 0.3,
        medium_threshold: float = 0.7,
        fast_rate: float = 0.15,
        medium_rate: float = 0.05,
        slow_rate: float = 0.01,
        minimum_retention_days: int = 14,
        minimum_evidence: int = 5,
    ):
        self.fast_threshold = fast_threshold
        self.medium_threshold = medium_threshold
        self.fast_rate = fast_rate
        self.medium_rate = medium_rate
        self.slow_rate = slow_rate
        self.minimum_retention_days = minimum_retention_days
        self.minimum_evidence = minimum_evidence
    
    def get_decay_rate(self, confidence: float) -> float:
        """Get decay rate based on confidence."""
        if confidence < self.fast_threshold:
            return self.fast_rate
        elif confidence < self.medium_threshold:
            return self.medium_rate
        else:
            return self.slow_rate
    
    def apply_decay(self, item: KnowledgeItem) -> float:
        """Apply decay to knowledge item confidence."""
        # Skip superseded items (already merged)
        if item.superseded_by:
            return item.confidence
        
        # Minimum retention check
        if item.total_evidence_count < self.minimum_evidence:
            days_since_creation = (datetime.now() - item.first_seen).days
            if days_since_creation < self.minimum_retention_days:
                return item.confidence
        
        # Calculate decay
        rate = self.get_decay_rate(item.confidence)
        days_inactive = (datetime.now() - item.last_seen).days
        steps = days_inactive // 7
        
        new_confidence = item.confidence - (rate * steps)
        
        # Auto-reinforce CANONICAL
        if item.phase == Phase.CANONICAL and item.confidence > 0.9:
            new_confidence = min(1.0, new_confidence + 0.01)
        
        return max(0.0, new_confidence)
    
    def calculate_vitality(self, item: KnowledgeItem) -> Vitality:
        """Calculate new vitality based on confidence and activity."""
        # Skip superseded items (already merged)
        if item.superseded_by:
            return item.vitality
        
        days_since_hit = 0
        if item.last_hit_at:
            days_since_hit = (datetime.now() - item.last_hit_at).days
        
        # ACTIVE -> DECAYING
        if item.vitality == Vitality.ACTIVE:
            if item.confidence < 0.5 or days_since_hit > 30:
                return Vitality.DECAYING
        
        # DECAYING -> ACTIVE (re-activation)
        if item.vitality == Vitality.DECAYING:
            if days_since_hit < 7:
                return Vitality.ACTIVE
        
        # DECAYING -> DORMANT
        if item.vitality == Vitality.DECAYING:
            if item.confidence < 0.2:
                return Vitality.DORMANT
        
        return item.vitality

class DecayEngine:
    """
    Engine for managing the lifecycle of memories (Episodic and Semantic).
    """
    def __init__(self, ttl_days: int = 30, semantic_decay_rate: float = 0.05, forget_threshold: float = 0.1):
        self.ttl_days = ttl_days
        self.semantic_decay_rate = semantic_decay_rate
        self.forget_threshold = forget_threshold

    def calculate_confidence(self, total_evidence_count: int = 0, stability_score: float = 0.0, 
                            hit_count: int = 0) -> float:
        """
        Вычисляет confidence на основе evidence, stability, и usage.
        
        Формула:
        - evidence_component (40%): log10(total_evidence_count + 1) / 2
        - stability_component (40%): stability_score
        - usage_component (20%): log1p(hit_count) / 2.3
        
        Returns: confidence (0.0 - 1.0)
        """
        # ⚡ Bolt: Use inline conditionals instead of min/max for bounds checking to eliminate Python function call overhead during mass evaluation

        # 1. Evidence component (0.0 - 1.0)
        # Логарифмическая шкала: 1 = 0.15, 10 = 0.5, 100 = 1.0
        ev_count = total_evidence_count if total_evidence_count > 0 else 0
        ev_val = math.log10(ev_count + 1) / 2
        evidence_component = ev_val if ev_val < 1.0 else 1.0
        
        # 2. Stability component (0.0 - 1.0)
        stab_val = stability_score if stability_score < 1.0 else 1.0
        stability_component = stab_val if stab_val > 0.0 else 0.0
        
        # 3. Usage component (0.0 - 1.0)
        # Логарифмическая шкала: 1 = 0.13, 10 = 0.43, 100 = 0.87
        hc = hit_count if hit_count > 0 else 0
        usg_val = math.log1p(hc) / 2.3
        usage_component = usg_val if usg_val < 1.0 else 1.0
        
        # Weighted average
        confidence = (
            evidence_component * 0.4 +
            stability_component * 0.4 +
            usage_component * 0.2
        )
        
        return round(confidence, 4)

    def evaluate_semantic(self, decisions: List[Dict[str, Any]]) -> List[Tuple[str, float, bool]]:
        """
        Analyzes semantic decisions and calculates confidence decay.
        Returns: List of (fid, new_confidence, should_forget)
        """
        now = datetime.now()
        results = []

        for dec in decisions:
            status = dec.get('status')
            kind = dec.get('kind')

            # Skip only non-decayable statuses
            if status not in ('active', 'deprecated', 'draft'):
                continue

            # Differentiated decay rate
            # Proposals decay at full rate (e.g. 0.05 per week)
            # Decisions/Constraints decay at 1/3 rate (slower)
            # Drafts decay at 2x rate (aggressive cleanup of incomplete work)
            effective_rate = self.semantic_decay_rate
            if kind in ('decision', 'constraint', 'assumption'):
                effective_rate = self.semantic_decay_rate / 3.0
            elif status == 'draft':
                # V7.6: Draft decay at 2x rate (aggressive cleanup)
                effective_rate = self.semantic_decay_rate * 2.0
            
            last_hit = dec.get('last_hit_at')
            if not last_hit:
                # If never hit, use creation timestamp
                last_hit = dec.get('timestamp')
            
            last_hit_dt = to_naive_utc(last_hit)
            if not last_hit_dt:
                last_hit_dt = now - timedelta(days=self.ttl_days)

            days_inactive = (now - last_hit_dt).days
            
            # Decay logic: inactivity check (min 7 days)
            if days_inactive > 7:
                decay_steps = days_inactive // 7
                current_conf = dec.get('confidence', 1.0)
                try:
                    current_conf = float(current_conf)
                except (ValueError, TypeError):
                    current_conf = 1.0

                # ⚡ Bolt: Inline boundary check avoids max() call
                new_conf_raw = current_conf - (effective_rate * decay_steps)
                new_conf = new_conf_raw if new_conf_raw > 0.0 else 0.0
                
                # Deletion threshold (cleanup trash)
                try:
                    should_forget = new_conf < float(self.forget_threshold)
                except (ValueError, TypeError):
                    should_forget = False

                results.append((dec['fid'], round(new_conf, 2), should_forget))
                
        return results

    def evaluate(self, events: List[Dict[str, Any]]) -> Tuple[List[int], List[int], int]:
        """
        Analyzes events and decides their fate based on age and links.
        
        Logic: 
        1. If linked_id is NOT NULL -> Keep forever (Immortal Link).
        2. If kind is decision or constraint -> Keep forever (Immortal Kind).
        3. If older than TTL and 'active' -> Move to archive.
        4. If older than TTL and 'archived' -> Physical prune.
        """

        now = datetime.now()
        to_archive = []
        to_prune = []
        retained_count = 0
        
        for ev in events:
            # I2 Integrity: Immortal episodes
            if ev.get('linked_id') or ev.get('kind') in ('decision', 'constraint'):
                retained_count += 1
                continue
            
            ts = to_naive_utc(ev.get('timestamp'))
            if not ts:
                ts = datetime.min
            
            age = now - ts
            
            if age > timedelta(days=self.ttl_days):
                if ev.get('status') == 'active':
                    to_archive.append(ev['id'])
                else:
                    to_prune.append(ev['id'])
                    
        return to_archive, to_prune, retained_count
