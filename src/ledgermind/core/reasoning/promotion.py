from typing import Optional
from ledgermind.core.core.knowledge import KnowledgeItem, Phase

class PromotionEngine:
    """Phase promotion engine."""
    
    def __init__(
        self,
        pattern_to_emergent_evidence: int = 20,
        pattern_to_emergent_coverage: float = 0.2,
        pattern_to_emergent_alt_evidence: int = 10,
        pattern_to_emergent_alt_confidence: float = 0.5,
        emergent_to_canonical_evidence: int = 50,
        emergent_to_canonical_stability: float = 0.5,
        emergent_to_canonical_coverage: float = 0.2,
        emergent_to_canonical_alt_confidence: float = 0.75,
    ):
        self.pattern_to_emergent_evidence = pattern_to_emergent_evidence
        self.pattern_to_emergent_coverage = pattern_to_emergent_coverage
        self.pattern_to_emergent_alt_evidence = pattern_to_emergent_alt_evidence
        self.pattern_to_emergent_alt_confidence = pattern_to_emergent_alt_confidence
        self.emergent_to_canonical_evidence = emergent_to_canonical_evidence
        self.emergent_to_canonical_stability = emergent_to_canonical_stability
        self.emergent_to_canonical_coverage = emergent_to_canonical_coverage
        self.emergent_to_canonical_alt_confidence = emergent_to_canonical_alt_confidence
    
    def check_promotion(self, item: KnowledgeItem) -> Optional[Phase]:
        """Check if item should be promoted."""
        if item.phase == Phase.PATTERN:
            return self._check_pattern_to_emergent(item)
        elif item.phase == Phase.EMERGENT:
            return self._check_emergent_to_canonical(item)
        return None
    
    def _check_pattern_to_emergent(self, item: KnowledgeItem) -> Optional[Phase]:
        """Check PATTERN -> EMERGENT."""
        # Standard path
        if (item.total_evidence_count >= self.pattern_to_emergent_evidence and
            item.coverage >= self.pattern_to_emergent_coverage):
            return Phase.EMERGENT
        
        # Alternative path
        if (item.confidence >= self.pattern_to_emergent_alt_confidence and
            item.total_evidence_count >= self.pattern_to_emergent_alt_evidence):
            return Phase.EMERGENT
        
        return None
    
    def _check_emergent_to_canonical(self, item: KnowledgeItem) -> Optional[Phase]:
        """Check EMERGENT -> CANONICAL."""
        # Standard path
        if (item.total_evidence_count >= self.emergent_to_canonical_evidence and
            item.stability_score >= self.emergent_to_canonical_stability and
            item.coverage >= self.emergent_to_canonical_coverage):
            return Phase.CANONICAL
        
        # Alternative path
        if (item.confidence >= self.emergent_to_canonical_alt_confidence and
            item.stability_score >= self.emergent_to_canonical_stability):
            return Phase.CANONICAL
        
        return None
