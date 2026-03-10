from typing import List, Dict, Any
import uuid
import logging
from .types import MemoryProtocol

logger = logging.getLogger("ledgermind.core.merging.builder")

class ProposalBuilder:
    """
    Builder pattern for step-by-step creation of a merge proposal.
    Returns a flat dictionary that is automatically processed by SemanticStore.save().
    """
    
    def __init__(self, memory: MemoryProtocol):
        self._memory = memory
        self._proposal = {
            "id": self._generate_unique_id(),
            "target_ids": [],
            "supersedes": [],
            "target": "knowledge_merge",
            "topic": "Automatic Merge",
            "confidence": 0.0,
            "enrichment_status": "pending" # Only stage tracking, no lifecycle status
        }

    def _generate_unique_id(self) -> str:
        """Generates a unique identifier."""
        return f"proposal_{uuid.uuid4().hex[:12]}"

    def set_topic(self, topic: str) -> 'ProposalBuilder':
        """Sets the merge topic."""
        if topic: self._proposal["topic"] = topic
        return self

    def set_target(self, target: str) -> 'ProposalBuilder':
        """Sets the proposal target (e.g., knowledge_merge)."""
        if target: self._proposal["target"] = target
        return self

    def add_target(self, target_id: str) -> 'ProposalBuilder':
        """Adds a target document ID to both lists for integrity."""
        if target_id and target_id not in self._proposal["target_ids"]:
            self._proposal["target_ids"].append(target_id)
            self._proposal["supersedes"].append(target_id)
        return self

    def set_confidence(self, confidence: float) -> 'ProposalBuilder':
        """Sets the confidence coefficient."""
        self._proposal["confidence"] = max(0.0, min(1.0, float(confidence)))
        return self

    def build(self) -> Dict[str, Any]:
        """
        Final build and validation of the proposal.
        """
        if len(self._proposal["target_ids"]) < 2:
            raise ValueError("Merging requires at least 2 targets.")
        
        logger.debug(f"Successfully built proposal {self._proposal['id']} with {len(self._proposal['target_ids'])} targets.")
        return self._proposal
