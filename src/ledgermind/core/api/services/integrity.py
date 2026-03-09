import logging
from typing import List, Dict, Any, Optional
from ..base_service import MemoryService
from ledgermind.core.reasoning.git_indexer import GitIndexer

logger = logging.getLogger("ledgermind.core.api.services.integrity")

class IntegrityService(MemoryService):
    """
    Service responsible for maintaining data integrity, manual linking, 
    forgetting memories, and Git synchronization.
    """
    
    def link_evidence(self, event_id: int, semantic_id: str):
        """Manually link an episodic event to a semantic record."""
        self.episodic.link_to_semantic(event_id, semantic_id)
        
        # Performance: Increment link_count in metadata
        with self.transaction(description=f"Link Evidence {event_id} -> {semantic_id}"):
            self.semantic.meta._conn.execute(
                "UPDATE semantic_meta SET link_count = link_count + 1 WHERE fid = ?",
                (semantic_id,)
            )

    def forget(self, decision_id: str):
        """Hard-deletes a memory across all stores."""
        self.semantic._validate_fid(decision_id)
        self.episodic.unlink_all_for_semantic(decision_id)
        self.semantic.purge_memory(decision_id)
        self.vector.remove_id(decision_id)
        logger.info(f"Memory {decision_id} forgotten.")

    def sync_git(self, memory_facade: Any, repo_path: str = ".", limit: int = 20) -> int:
        """Syncs recent Git commits into episodic memory."""
        indexer = GitIndexer(repo_path)
        return indexer.index_to_memory(memory_facade, limit=limit)
