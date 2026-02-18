from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

class DecayReport:
    """
    Summary of the results from a memory decay process.
    """
    def __init__(self, archived: int, pruned: int, retained: int):
        self.archived = archived
        self.pruned = pruned
        self.retained_by_link = retained

    def __repr__(self):
        return f"<DecayReport archived={self.archived}, pruned={self.pruned}, retained={self.retained_by_link}>"

class DecayEngine:
    """
    Engine for managing the lifecycle of episodic memories.
    """
    def __init__(self, ttl_days: int = 30):
        """
        Initialize with a specific Time-To-Live for episodic memories.
        """
        self.ttl_days = ttl_days

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
