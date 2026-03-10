import logging
import uuid
from contextlib import contextmanager
from typing import Generator, Dict, List, Any
from .types import MemoryProtocol

logger = logging.getLogger("ledgermind.core.merging.transaction")

class TransactionManager:
    """
    Context manager for managing merge transactions.
    Ensures safe interaction with semantic memory.
    """

    def __init__(self, memory: MemoryProtocol):
        self.memory = memory

    @contextmanager
    def transaction(self, description: str = "") -> Generator[None, None, None]:
        """
        Executes a block of code within a protected semantic memory transaction.
        """
        try:
            with self.memory.semantic.transaction():
                yield
        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            raise

    def create_proposal(self, data: Dict[str, Any]) -> str:
        """
        Creates a merge proposal and saves it in memory using MemoryEvent.
        """
        from ledgermind.core.core.schemas import MemoryEvent, KIND_PROPOSAL
        from datetime import datetime
        
        proposal_id = data.get("id") or f"proposal_{uuid.uuid4().hex[:12]}"
        
        # Simple wrapping: 
        # All fields go into context, SemanticStore.save() moves CORE_FIELDS to root.
        event = MemoryEvent(
            source="system",
            kind=KIND_PROPOSAL,
            content=data.get("topic", "Merge Proposal"),
            timestamp=datetime.now(),
            context=data 
        )
        
        try:
            # SemanticStore.save returns the relative path (FID)
            fid = self.memory.semantic.save(event)
            logger.info(f"Successfully created and saved new merge proposal: {fid}")
            return fid
        except Exception as e:
            logger.error(f"Error saving proposal {proposal_id} to memory: {e}")
            return proposal_id

    def lock_decisions(self, decision_ids: List[str], lock_reason: str) -> None:
        """
        Locks decisions by updating their status in metadata/files.
        """
        logger.debug(f"Locking {len(decision_ids)} decisions: {lock_reason}")
        for fid in decision_ids:
            try:
                self.memory.semantic.update_decision(fid, {"merge_status": "pending"}, 
                                                    f"Locking for merge: {lock_reason}")
            except Exception as e:
                logger.error(f"Error locking decision {fid}: {e}")

    def get_active_targets(self) -> List[str]:
        """
        Retrieves a list of active targets from metadata store.
        """
        try:
            all_meta = self.memory.semantic.meta.list_all()
            return list(set(m.get('target') for m in all_meta if m.get('status') == 'active'))
        except Exception as e:
            logger.error(f"Error retrieving active targets: {e}")
            return []
