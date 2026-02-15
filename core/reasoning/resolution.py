from typing import List, Optional, Set
from core.schemas import ResolutionIntent

class ResolutionEngine:
    def __init__(self, semantic_store_path: str):
        self.path = semantic_store_path

    def validate_intent(self, intent: ResolutionIntent, conflict_files: List[str]) -> bool:
        """
        Ensures that the intent covers all detected conflict files.
        """
        if intent.resolution_type == "abort":
            return False
            
        # Check if all actual conflicts are addressed in the intent
        addressed = set(intent.target_decision_ids)
        actual = set(conflict_files)
        
        # Intent must address at least all actual conflicts
        return actual.issubset(addressed)
