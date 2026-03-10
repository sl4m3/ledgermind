from typing import List, Dict, Any
import uuid
import logging
from .types import MemoryProtocol

logger = logging.getLogger("ledgermind.core.merging.builder")

class ProposalBuilder:
    """
    Builder pattern for step-by-step creation of a merge proposal.
    Prevents field duplication between root and context.
    """
    
    def __init__(self, memory: MemoryProtocol):
        self._memory = memory
        
        # System fields (will go to Root YAML)
        self._id = self._generate_unique_id()
        self._status = "pending"
        self._confidence = 0.0
        self._target = "knowledge_merge"
        self._supersedes = []
        
        # Domain fields (will go to Context)
        self._context = {
            "topic": "Automatic Merge",
            "target_ids": []
        }

    def _generate_unique_id(self) -> str:
        """Generates a unique identifier."""
        return f"proposal_{uuid.uuid4().hex[:12]}"

    def set_topic(self, topic: str) -> 'ProposalBuilder':
        """Sets the merge topic inside context."""
        if topic: self._context["topic"] = topic
        return self

    def set_target(self, target: str) -> 'ProposalBuilder':
        """Sets the proposal target (e.g., knowledge_merge)."""
        if target: self._target = target
        return self

    def add_target(self, target_id: str) -> 'ProposalBuilder':
        """Adds a target document ID to both lists."""
        if target_id and target_id not in self._context["target_ids"]:
            self._context["target_ids"].append(target_id)
            self._supersedes.append(target_id)
        return self

    def set_confidence(self, confidence: float) -> 'ProposalBuilder':
        """Sets the confidence coefficient."""
        self._confidence = max(0.0, min(1.0, float(confidence)))
        return self

    def build(self) -> Dict[str, Any]:
        """
        Returns a structured dictionary where system fields are clearly marked.
        """
        if len(self._context["target_ids"]) < 2:
            raise ValueError("Merging requires at least 2 targets.")
        
        # We pack system fields and pure context separately
        return {
            "id": self._id,
            "status": self._id, # TransactionManager uses this field name for saving
            "actual_status": self._status,
            "confidence": self._confidence,
            "target": self._target,
            "supersedes": self._supersedes,
            "context": self._context # This is the ONLY thing that should stay in context
        }
