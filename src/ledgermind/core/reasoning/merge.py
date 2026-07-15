import math
from datetime import datetime
from typing import Tuple
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality

class MergeEngine:
    """Multi-criteria merge engine with phase-aware thresholds."""
    
    def __init__(self):
        # Phase-aware thresholds
        self.thresholds = {
            Phase.PATTERN: 0.5,
            Phase.EMERGENT: 0.6,
            Phase.CANONICAL: 0.7,
        }
        self.dormant_threshold = 0.5
    
    def calculate_similarity(self, candidate: KnowledgeItem, target: KnowledgeItem) -> float:
        """Calculate comprehensive similarity score."""
        # Profile gate: different profiles → 0.0 similarity
        if candidate.profile != target.profile:
            return 0.0
        
        # Semantic similarity (simplified: same target = 1.0, else 0.5)
        target_score = 1.0 if candidate.target == target.target else 0.5
        
        # Phase compatibility
        phase_score = 1.0 if candidate.phase == target.phase else 0.5
        
        # Temporal proximity
        days_diff = abs((candidate.first_seen - target.first_seen).days)
        temporal_score = max(0.0, 1.0 - (days_diff / 30.0))
        
        # Weighted average
        similarity = (
            target_score * 0.4 +
            phase_score * 0.3 +
            temporal_score * 0.3
        )
        
        return similarity
    
    def assess_quality(self, item: KnowledgeItem) -> float:
        """Assess quality of knowledge item."""
        # Confidence (hit_count based)
        confidence_score = item.confidence
        
        # Stability (phase-aware)
        if item.phase == Phase.PATTERN:
            stability_score = 0.0  # Not a factor for PATTERN
        else:
            age_days = (datetime.now() - item.first_seen).days
            age_factor = min(1.0, age_days / 30.0)
            hit_factor = min(1.0, item.hit_count / 10.0)
            evidence_factor = min(1.0, item.total_evidence_count / 10.0)
            stability_score = age_factor * 0.3 + hit_factor * 0.3 + evidence_factor * 0.4
        
        # Evidence
        evidence_score = min(1.0, item.total_evidence_count / 10.0)
        
        # Age
        age_days = (datetime.now() - item.first_seen).days
        age_score = min(1.0, age_days / 30.0)
        
        # Weighted quality
        quality = (
            confidence_score * 0.3 +
            stability_score * 0.3 +
            evidence_score * 0.2 +
            age_score * 0.2
        )
        
        return quality
    
    def get_threshold(self, phase: Phase) -> float:
        """Get merge threshold for phase."""
        return self.thresholds.get(phase, 0.6)
    
    def should_merge(self, candidate: KnowledgeItem, target: KnowledgeItem) -> bool:
        """Multi-criteria merge decision."""
        # Profile gate: different profiles → SKIP
        if candidate.profile != target.profile:
            return False
        
        # Calculate similarity
        similarity = self.calculate_similarity(candidate, target)
        
        # Calculate quality
        candidate_quality = self.assess_quality(candidate)
        target_quality = self.assess_quality(target)
        avg_quality = (candidate_quality + target_quality) / 2
        
        # Calculate base merge score
        base_score = similarity * 0.5 + avg_quality * 0.5
        
        # Session boost: only if similarity > 0.6
        if (candidate.session_id == target.session_id and 
            candidate.session_id and
            similarity > 0.6):
            session_boost = similarity * 0.15
        else:
            session_boost = 0
        
        merge_score = min(1.0, base_score + session_boost)
        
        # Get threshold based on higher phase
        phase_order = {Phase.PATTERN: 1, Phase.EMERGENT: 2, Phase.CANONICAL: 3}
        higher_phase = max(candidate.phase, target.phase, key=lambda p: phase_order[p])
        threshold = self.get_threshold(higher_phase)
        
        # DORMANT: lower threshold (revive through merge)
        if candidate.vitality == Vitality.DORMANT or \
           target.vitality == Vitality.DORMANT:
            threshold = self.dormant_threshold
        
        return merge_score >= threshold
    
    def choose_stronger(self, candidate: KnowledgeItem, target: KnowledgeItem) -> Tuple[KnowledgeItem, KnowledgeItem]:
        """Choose stronger knowledge item for merge."""
        if candidate.confidence >= target.confidence:
            return candidate, target
        else:
            return target, candidate
    
    def execute_supersede(self, stronger: KnowledgeItem, weaker: KnowledgeItem) -> None:
        """Execute supersede: mark weaker as superseded."""
        weaker.superseded_by = stronger.fid
        stronger.supersedes.append(weaker.fid)
        
        # Update evidence count (accumulative)
        stronger.total_evidence_count = (
            stronger.total_evidence_count + 
            weaker.total_evidence_count + 1
        )
        
        # Update phase (take higher)
        phase_order = {Phase.PATTERN: 1, Phase.EMERGENT: 2, Phase.CANONICAL: 3}
        if phase_order[weaker.phase] > phase_order[stronger.phase]:
            stronger.phase = weaker.phase
