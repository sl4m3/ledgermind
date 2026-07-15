import math
from datetime import datetime
from typing import Dict, List, Optional
from ledgermind.core.core.knowledge import KnowledgeItem

def calculate_confidence(hit_count: int) -> float:
    """Calculate confidence from hit_count."""
    return min(1.0, math.log1p(hit_count) / 2.3)

def calculate_stability(
    total_evidence_count: int,
    intervals: List[float],
    lifetime_days: float,
) -> float:
    """Calculate stability score from evidence intervals."""
    if total_evidence_count < 2:
        return 0.0
    
    if len(intervals) < 2:
        return 0.0
    
    import statistics
    variance = statistics.variance(intervals)
    delta_stability = max(0.0, 1.0 - (variance / (lifetime_days + 1.0)))
    age_factor = min(1.0, lifetime_days / 7.0)
    
    return delta_stability * (0.5 + 0.5 * age_factor)

def calculate_coverage(first_seen: datetime, last_seen: datetime) -> float:
    """Calculate coverage from temporal boundaries."""
    observation_window_days = 30.0
    lifetime_days = (last_seen - first_seen).total_seconds() / 86400
    return min(1.0, lifetime_days / observation_window_days)

def calculate_utility(
    stability_score: float,
    confidence: float,
    coverage: float,
) -> float:
    """Calculate utility from metrics."""
    return min(1.0, max(0.0, stability_score * 0.3 + confidence * 0.5 + coverage * 0.2))

def count_evidence(item_fid: str, items: Dict[str, any]) -> int:
    """Count evidence using accumulative merge count."""
    item = items.get(item_fid)
    if not item:
        return 0
    
    count = len(item.supersedes)
    for fid in item.supersedes:
        if fid in items:
            count += count_evidence(fid, items)
    
    return count
