from typing import List, Dict, Any
import uuid
import logging
from .types import MemoryProtocol

logger = logging.getLogger("ledgermind.core.merging.builder")

class ProposalBuilder:
    """
    Builder pattern for step-by-step creation of a merge proposal.
    Provides data validation during the build process.
    """
    
    def __init__(self, memory: MemoryProtocol):
        """
        Initializes the Builder.
        
        Args:
            memory: Memory object for ID uniqueness validation.
        """
        self._memory = memory
        self._proposal = {
            "id": self._generate_unique_id(),
            "target_ids": [],
            "topic": "Automatic Merge",
            "confidence": 0.0,
            "status": "pending"
        }

    def _generate_unique_id(self) -> str:
        """
        Generates a unique identifier for the proposal.
        Checks for collisions in memory.
        """
        new_id = f"proposal_{uuid.uuid4().hex[:12]}"
        try:
            all_docs = self._memory.semantic.meta.list_all()
            existing_ids = {doc.get('id') for doc in all_docs}
            while new_id in existing_ids:
                new_id = f"proposal_{uuid.uuid4().hex[:12]}"
        except Exception as e:
            logger.warning(f"Failed to check ID uniqueness in memory: {e}")
        return new_id

    def set_topic(self, topic: str) -> 'ProposalBuilder':
        """Sets the merge topic."""
        if not topic or not isinstance(topic, str):
            logger.warning("Incorrect merge topic provided, using default value.")
        else:
            self._proposal["topic"] = topic
        return self

    def add_target(self, target_id: str) -> 'ProposalBuilder':
        """Adds a target document ID to the merge list."""
        if target_id and isinstance(target_id, str) and target_id not in self._proposal["target_ids"]:
            self._proposal["target_ids"].append(target_id)
        else:
            logger.debug(f"Target {target_id} ignored (empty, wrong type, or already added).")
        return self

    def set_confidence(self, confidence: float) -> 'ProposalBuilder':
        """Sets the confidence coefficient (from 0.0 to 1.0)."""
        self._proposal["confidence"] = max(0.0, min(1.0, float(confidence)))
        return self

    def build(self) -> Dict[str, Any]:
        """
        Final build and validation of the proposal.
        
        Returns:
            Dictionary with proposal data.
            
        Raises:
            ValueError: If fewer than 2 targets are added.
        """
        if len(self._proposal["target_ids"]) < 2:
            raise ValueError("Merging requires at least 2 targets.")
        
        logger.debug(f"Successfully built proposal {self._proposal['id']} with {len(self._proposal['target_ids'])} targets.")
        return self._proposal
