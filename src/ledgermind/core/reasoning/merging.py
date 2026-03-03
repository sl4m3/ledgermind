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
                
                # ENHANCED: Use title, content, and keywords for a robust semantic fingerprint
                title = data.get("title") or data.get("context", {}).get("title", "")
                content_desc = data.get("content") or data.get("context", {}).get("content", "")
                keywords = data.get("context", {}).get("keywords", [])
                keywords_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)

                search_query = f"{title} {content_desc} {keywords_str}".strip()
                if not search_query: continue
                
                # Search for duplicates
                # We use a strict threshold
                results = self.memory.search_decisions(search_query, limit=5, mode="strict")
                
                # Normalize scores by the maximum found to account for lifecycle multipliers (Issue #10)
                max_score = max((r['score'] for r in results), default=1.0)
                
                duplicates = []
                total_norm_score = 0
                for res in results:
                    normalized_score = res['score'] / max_score if max_score > 0 else 0
                    if res['id'] != fid and normalized_score >= threshold:
                        duplicates.append(res)
                        total_norm_score += normalized_score
                
                if duplicates:
                    # Calculate dynamic confidence as average similarity
                    avg_confidence = total_norm_score / len(duplicates)
                    
                    target_ids = [d['id'] for d in duplicates] + [fid]
                    # Create a proposal to merge them
                    proposal_id = self._create_merge_proposal(
                        target_ids, 
                        title or search_query[:50],
                        confidence=avg_confidence
                    )
                    if proposal_id:
                        proposals.append(proposal_id)
                        
            except Exception as e:
                logger.error(f"Error scanning {fid}: {e}")
                continue
                
        return proposals

    def _create_merge_proposal(self, target_ids: List[str], topic: str, confidence: float = 0.90) -> Optional[str]:
        # Check if proposal already exists for these targets? 
        # For now just create one.
        
        target_ids = sorted(list(set(target_ids))) # Deduplicate and sort
        if len(target_ids) < 2: return None
        
        title = f"Knowledge Consolidation: {topic[:50]}..."
        
        # Technical Intent Statement (Rationale)
        rationale = (
            f"Detected fragmented knowledge across {len(target_ids)} semantically identical entries.\n\n"
            f"The identified decisions ({', '.join(target_ids)}) represent overlapping architectural "
            f"patterns or procedural guides related to '{topic}'.\n\n"
            f"Consolidation is necessary to maintain a Single Source of Truth and improve "
            f"knowledge retrieval precision. This proposal initiates a synthesis to merge these "
            f"into a single canonical guide."
        )
        
        # Prepare context data
        ctx_data = {
            "title": title,
            "target": "knowledge_merge",
            "status": "draft",
            "rationale": rationale,
            "confidence": round(confidence, 4),
            "suggested_supersedes": target_ids,
            "enrichment_status": "pending",  # Signal for LLMEnricher to synthesize
            "strengths": ["Reduces redundancy", "Improves retrieval precision"],
            "suggested_consequences": ["Original decisions will be superseded and archived"]
        }
        
        try:
            decision = self.memory.process_event(
                source="system",
                kind=KIND_PROPOSAL,
                content=title,
                context=ctx_data
            )
            return decision.metadata.get("file_id")
        except Exception as e:
            logger.error(f"Failed to create merge proposal: {e}")
            return None
