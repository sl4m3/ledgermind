from typing import Any, Dict, Optional
from datetime import datetime, timedelta

class RankingPolicy:
    """
    Implements the scoring logic for Hybrid Search.
    Weights:
    - Vector Similarity (Base)
    - Semantic Status (Active/Superseded)
    - Temporal Recency
    - Source Authority
    """
    
    # Weights configuration
    WEIGHT_VECTOR_SIMILARITY = 1.0
    BONUS_ACTIVE_STATUS = 1.5      # Massive boost for being the current truth
    PENALTY_SUPERSEDED = 0.1       # Heavy penalty for outdated info (multiplicative)
    BONUS_HUMAN_AUTHORITY = 0.2    # Bonus for human-authored decisions
    
    # Temporal decay settings
    DECAY_HALFLIFE_DAYS = 90       # Score halves every 90 days for non-active items

    @staticmethod
    def calculate_score(vector_score: float, 
                        metadata: Dict[str, Any], 
                        timestamp: Optional[datetime] = None) -> float:
        """
        Calculates the final relevance score.
        """
        score = vector_score * RankingPolicy.WEIGHT_VECTOR_SIMILARITY
        
        status = metadata.get("status", "unknown")
        
        # 1. Semantic Status Policy
        if status == "active":
            score += RankingPolicy.BONUS_ACTIVE_STATUS
        elif status == "superseded":
            score *= RankingPolicy.PENALTY_SUPERSEDED
        elif status == "deprecated":
            score *= 0.05 # Almost invisible
            
        # 2. Authority Policy
        rationale = str(metadata.get("rationale", ""))
        if "[via MCP]" not in rationale:
            score += RankingPolicy.BONUS_HUMAN_AUTHORITY
            
        # 3. Temporal Policy (only applies if scores are close or for sorting history)
        # Active decisions are timeless, but for audit/history, recency matters.
        if timestamp:
            age_days = (datetime.now() - timestamp).days
            if age_days > 0:
                # Simple linear decay for now, or exponential if needed
                # For active items, age doesn't reduce relevance, but might slightly boost "freshness"
                pass 
                
        return round(score, 4)
