from dataclasses import dataclass
from typing import List
from ledgermind.core.core.knowledge import KnowledgeItem
from ledgermind.core.reasoning.decay import NewDecayEngine
from ledgermind.core.reasoning.merge import MergeEngine
from ledgermind.core.reasoning.promotion import PromotionEngine

@dataclass
class PipelineResult:
    merge_count: int
    decay_count: int
    promote_count: int

class LifecyclePipeline:
    """Sequential pipeline: Merge -> Decay -> Promote."""
    
    def __init__(self):
        self.decay_engine = NewDecayEngine()
        self.merge_engine = MergeEngine()
        self.promotion_engine = PromotionEngine()
    
    def run(self, items: List[KnowledgeItem]) -> PipelineResult:
        """Run pipeline on knowledge items."""
        merge_count = 0
        decay_count = 0
        promote_count = 0
        
        # Step 1: Merge (first - claim candidates)
        claimed = set()  # Track claimed proposals
        for i, candidate in enumerate(items):
            if candidate.fid in claimed:
                continue
            
            for j, target in enumerate(items[i+1:], i+1):
                if target.fid in claimed:
                    continue
                
                if self.merge_engine.should_merge(candidate, target):
                    # Claim both candidates
                    claimed.add(candidate.fid)
                    claimed.add(target.fid)
                    
                    # Execute merge
                    stronger, weaker = self.merge_engine.choose_stronger(candidate, target)
                    self.merge_engine.execute_supersede(stronger, weaker)
                    merge_count += 1
        
        # Step 2: Decay (second - after merge)
        for item in items:
            new_confidence = self.decay_engine.apply_decay(item)
            if new_confidence != item.confidence:
                item.confidence = new_confidence
                decay_count += 1
            
            new_vitality = self.decay_engine.calculate_vitality(item)
            if new_vitality != item.vitality:
                item.vitality = new_vitality
        
        # Step 3: Promote (last)
        for item in items:
            new_phase = self.promotion_engine.check_promotion(item)
            if new_phase:
                item.phase = new_phase
                promote_count += 1
        
        return PipelineResult(
            merge_count=merge_count,
            decay_count=decay_count,
            promote_count=promote_count,
        )
