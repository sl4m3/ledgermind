import logging
from typing import List, Optional
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import ProposalContent, KIND_PROPOSAL

logger = logging.getLogger("ledgermind-core.merging")

class MergeEngine:
    """
    Scans for semantically identical knowledge and proposes merges.
    """
    def __init__(self, memory: Memory):
        self.memory = memory

    def scan_for_duplicates(self, threshold: float = 0.85) -> List[str]:
        """
        Scans active decisions and creates proposals for merging duplicates.
        Returns list of created proposal IDs.
        """
        active_ids = self.memory.get_decisions()
        proposals = []
        
        # This is O(N^2) naive scan or O(N) search. 
        # For efficiency, we only check the N most recent decisions against the whole base.
        # But we need access to embeddings.
        
        # Let's rely on 'search' being efficient.
        # Check specific recent decisions
        recent_ids = active_ids[:20] 
        
        for fid in recent_ids:
            try:
                # We need the text content to search
                # Currently Memory doesn't expose 'get_content(fid)' easily without reading file
                # But we can assume we have it via search or load.
                
                # Let's read the file to get content
                import os
                from ledgermind.core.stores.semantic_store.loader import MemoryLoader
                
                path = os.path.join(self.memory.semantic.repo_path, fid)
                with open(path, 'r', encoding='utf-8') as f:
                    data, _ = MemoryLoader.parse(f.read())
                
                content = data.get("content") or data.get("context", {}).get("title")
                if not content: continue
                
                # Search for duplicates
                # We use a strict threshold
                results = self.memory.search_decisions(content, limit=5, mode="strict")
                
                duplicates = []
                for res in results:
                    if res['id'] != fid and res['score'] >= threshold:
                        duplicates.append(res)
                
                if duplicates:
                    target_ids = [d['id'] for d in duplicates] + [fid]
                    # Create a proposal to merge them
                    proposal_id = self._create_merge_proposal(target_ids, content)
                    if proposal_id:
                        proposals.append(proposal_id)
                        
            except Exception as e:
                logger.error(f"Error scanning {fid}: {e}")
                continue
                
        return proposals

    def _create_merge_proposal(self, target_ids: List[str], topic: str) -> Optional[str]:
        # Check if proposal already exists for these targets? 
        # For now just create one.
        
        target_ids = sorted(list(set(target_ids))) # Deduplicate and sort
        if len(target_ids) < 2: return None
        
        title = f"Merge Duplicates: {topic[:30]}..."
        target_namespace = "maintenance" # or use the namespace of the decisions
        
        rationale = f"Detected {len(target_ids)} semantically identical decisions. Suggesting merge to reduce fragmentation."
        
        ctx = ProposalContent(
            title=title,
            target="knowledge_merge",
            status="draft",
            rationale=rationale,
            confidence=0.99,
            suggested_supersedes=target_ids,
            strengths=["Reduces redundancy", "Improves retrieval precision"],
            suggested_consequences=["Original decisions will be superseded"]
        )
        
        try:
            decision = self.memory.process_event(
                source="system",
                kind=KIND_PROPOSAL,
                content=title,
                context=ctx
            )
            return decision.metadata.get("file_id")
        except Exception as e:
            logger.error(f"Failed to create merge proposal: {e}")
            return None
