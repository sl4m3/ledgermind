from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
import math
from ledgermind.core.utils.datetime_utils import to_naive_utc

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
        # 1. Evidence component (0.0 - 1.0)
        # Логарифмическая шкала: 1 = 0.15, 10 = 0.5, 100 = 1.0
        evidence_component = min(1.0, math.log10(max(0, total_evidence_count) + 1) / 2)
        
        # 2. Stability component (0.0 - 1.0)
        stability_component = max(0.0, min(1.0, stability_score))
        
        # 3. Usage component (0.0 - 1.0)
        # Логарифмическая шкала: 1 = 0.13, 10 = 0.43, 100 = 0.87
        usage_component = min(1.0, math.log1p(max(0, hit_count)) / 2.3)
        
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
            
            if status not in ('active', 'deprecated', 'draft'):
                continue
            
            # Differentiated decay rate
            # Proposals decay at full rate (e.g. 0.05 per week)
            # Decisions/Constraints decay at 1/3 rate (slower)
            # Drafts decay at 2x rate (aggressive cleanup)
            effective_rate = self.semantic_decay_rate
            if kind in ('decision', 'constraint', 'assumption'):
                effective_rate = self.semantic_decay_rate / 3.0
            elif status == 'draft':
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

                new_conf = max(0.0, current_conf - (effective_rate * decay_steps))
                
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
