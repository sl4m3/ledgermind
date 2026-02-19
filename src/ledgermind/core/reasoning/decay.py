from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

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

    def evaluate_semantic(self, decisions: List[Dict[str, Any]]) -> List[Tuple[str, float, bool]]:
        """
        Analyzes semantic decisions and calculates confidence decay.
        Returns: List of (fid, new_confidence, should_forget)
        """
        now = datetime.now()
        results = []
        
        for dec in decisions:
            # Only apply decay to active proposals.
            # Permanent 'decisions' should NEVER decay based on hit counts.
            if dec.get('status') != 'active': continue
            if dec.get('kind') != 'proposal': continue
            
            last_hit = dec.get('last_hit_at')
            if not last_hit:
                # If never hit, use creation timestamp
                last_hit = dec.get('timestamp')
            
            try:
                if isinstance(last_hit, str):
                    last_hit_dt = datetime.fromisoformat(last_hit)
                else:
                    last_hit_dt = last_hit
            except (ValueError, TypeError):
                last_hit_dt = now - timedelta(days=self.ttl_days)

            days_inactive = (now - last_hit_dt).days
            
            # Decay logic: -0.05 confidence per month (30 days) of inactivity
            # but only if inactive for more than 7 days
            if days_inactive > 7:
                decay_steps = days_inactive // 7
                current_conf = dec.get('confidence', 1.0)
                new_conf = max(0.0, current_conf - (self.semantic_decay_rate * decay_steps))
                
                should_forget = new_conf < self.forget_threshold
                results.append((dec['fid'], round(new_conf, 2), should_forget))
                
        return results

    def evaluate(self, events: List[Dict[str, Any]]) -> Tuple[List[int], List[int], int]:
        """
        Analyzes events and decides their fate based on age and links.
        
        Logic: 
        1. If linked_id is NOT NULL -> Keep forever (Immortal Link).
        2. If older than TTL and 'active' -> Move to archive.
        3. If older than TTL and 'archived' -> Physical prune.
        """

        now = datetime.now()
        to_archive = []
        to_prune = []
        retained_count = 0
        
        for ev in events:
            # I2 Integrity: Immortal episodes
            if ev.get('linked_id'):
                retained_count += 1
                continue
            
            try:
                ts = datetime.fromisoformat(ev['timestamp'])
            except (ValueError, TypeError):
                # If timestamp is invalid, treat it as very old to trigger archive/prune
                ts = datetime.min
            
            age = now - ts
            
            if age > timedelta(days=self.ttl_days):
                if ev.get('status') == 'active':
                    to_archive.append(ev['id'])
                else:
                    to_prune.append(ev['id'])
                    
        return to_archive, to_prune, retained_count
