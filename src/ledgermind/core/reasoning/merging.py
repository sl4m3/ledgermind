import logging
import json
from typing import List, Optional, Set
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import ProposalContent, KIND_PROPOSAL

logger = logging.getLogger("ledgermind-core.merging")

class MergeEngine:
    """
    Scans for semantically identical knowledge and proposes merges.
    """
    def __init__(self, memory: Memory):
        self.memory = memory

    def _get_active_merge_targets(self) -> Set[str]:
        """Returns a set of decision IDs already pending for a merge."""
        targets = set()
        # Direct SQLite query via metadata store for efficiency
        metas = self.memory.semantic.meta.list_all()
        for m in metas:
            if m.get('status') == 'draft' and m.get('kind') == KIND_PROPOSAL:
                try:
                    ctx = json.loads(m.get('context_json', '{}'))
                    supersedes = ctx.get('suggested_supersedes', [])
                    targets.update(supersedes)
                except: continue
        return targets

    def scan_for_duplicates(self, threshold: float = 0.65) -> List[str]:
        """
        Scans active decisions and creates proposals for merging duplicates.
        Returns list of created proposal IDs.
        """
        active_ids = self.memory.get_decisions()
        proposals = []
        
        # Protect against merge loops (don't propose merge for files already in a draft merge)
        pending_targets = self._get_active_merge_targets()
        
        # Check all active decisions against the whole base
        for fid in active_ids:
            if fid in pending_targets:
                continue

            try:
                # We need the text content to search
                import os
                from ledgermind.core.stores.semantic_store.loader import MemoryLoader
                
                path = os.path.join(self.memory.semantic.repo_path, fid)
                if not os.path.exists(path): continue

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
                results = self.memory.search_decisions(search_query, limit=5, mode="strict")
                
                # Normalize scores
                max_score = max((r['score'] for r in results), default=1.0)
                
                duplicates = []
                total_norm_score = 0
                for res in results:
                    normalized_score = res['score'] / max_score if max_score > 0 else 0
                    # Skip self and already pending targets
                    if res['id'] != fid and res['id'] not in pending_targets and normalized_score >= threshold:
                        duplicates.append(res)
                        total_norm_score += normalized_score
                
                if duplicates:
                    avg_confidence = total_norm_score / len(duplicates)
                    target_ids = [d['id'] for d in duplicates] + [fid]
                    
                    # Logic for automatic consolidation vs validation
                    # Threshold for auto-merge is 0.85
                    target_mode = "knowledge_merge" if avg_confidence >= 0.85 else "knowledge_validation"
                    
                    proposal_id = self._create_merge_proposal(
                        target_ids, 
                        title or search_query[:50],
                        confidence=avg_confidence,
                        target=target_mode
                    )
                    if proposal_id:
                        proposals.append(proposal_id)
                        # Add new targets to pending set to avoid duplicates within same run
                        pending_targets.update(target_ids)
                        
            except Exception as e:
                logger.error(f"Error scanning {fid}: {e}")
                continue
                
        return proposals

    def _create_merge_proposal(self, target_ids: List[str], topic: str, confidence: float = 0.90, target: str = "knowledge_merge") -> Optional[str]:
        target_ids = sorted(list(set(target_ids))) 
        if len(target_ids) < 2: return None
        
        is_validation = target == "knowledge_validation"
        title = f"{'Validate' if is_validation else 'Consolidate'} Knowledge: {topic[:50]}..."
        
        # Technical Intent Statement
        if is_validation:
            rationale = (
                f"POTENTIAL DUPLICATION: {len(target_ids)} entries found with moderate similarity ({confidence:.2%}).\n\n"
                f"Entries: {', '.join(target_ids)}\n\n"
                f"LLM validation is required to determine if these entries should be merged or kept separate. "
                f"If they are duplicates, a synthesis will be performed."
            )
        else:
            rationale = (
                f"Detected fragmented knowledge across {len(target_ids)} semantically identical entries.\n\n"
                f"The identified decisions ({', '.join(target_ids)}) represent overlapping architectural "
                f"patterns or procedural guides related to '{topic}'.\n\n"
                f"Consolidation is necessary to maintain a Single Source of Truth."
            )
        
        ctx_data = {
            "title": title,
            "target": target,
            "status": "draft",
            "rationale": rationale,
            "confidence": round(confidence, 4),
            "suggested_supersedes": target_ids,
            "enrichment_status": "pending",
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
