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

    def scan_for_duplicates(self, threshold: float = 0.75) -> List[str]:
        """
        Scans enriched decisions and creates proposals for merging or disambiguation.
        Handles both semantic similarity and structural I4 violations.
        """
        # 1. Get all active and enriched decisions
        all_metas = self.memory.semantic.meta.list_all()
        enriched_metas = [
            m for m in all_metas 
            if m.get('status') == 'active' and m.get('enrichment_status') == 'completed'
        ]

        if not enriched_metas:
            return []

        proposals = []
        pending_targets = self._get_active_merge_targets()

        # --- PHASE A: STRUCTURAL CONFLICT DETECTION (I4 Resolution) ---
        # Group by EXACT target to find multiple active decisions for the same path.
        # This handles cases where different concepts share the same name.
        target_groups = {}
        for m in enriched_metas:
            t = m.get('target')
            if not t or m['fid'] in pending_targets: continue
            if t not in target_groups: target_groups[t] = []
            target_groups[t].append(m['fid'])
            
        for target, fids in target_groups.items():
            if len(fids) > 1:
                logger.info(f"Structural Conflict: {len(fids)} active decisions for target '{target}'. Creating disambiguation proposal.")
                # We use knowledge_validation here to let LLM decide: Merge or Rename?
                proposal_id = self._create_merge_proposal(
                    fids, 
                    target,
                    confidence=0.8, # Validation mode (not auto-merge)
                    target="knowledge_validation"
                )
                if proposal_id:
                    proposals.append(proposal_id)
                    pending_targets.update(fids)

        # --- PHASE B: SEMANTIC CONSOLIDATION ---
        # Optimization: Only initiate search FROM the most recent decisions (last 50)
        recent_candidates = sorted(enriched_metas, key=lambda x: x.get('timestamp', ''), reverse=True)[:50]
        
        for m in recent_candidates:
            fid = m['fid']
            if fid in pending_targets:
                continue

            try:
                # Use title and content for semantic fingerprint
                title = m.get('title') or ""
                content_desc = m.get('content') or ""
                keywords = m.get('keywords') or ""

                search_query = f"{title} {content_desc} {keywords}".strip()
                if not search_query: continue
                
                # Search against ALL active decisions
                results = self.memory.search_decisions(search_query, limit=10, mode="strict")
                
                # Normalize scores
                max_score = max((r['score'] for r in results), default=1.0)
                
                duplicates = []
                total_norm_score = 0
                
                for res in results:
                    res_fid = res['id']
                    # Skip self and already pending targets
                    if res_fid == fid or res_fid in pending_targets:
                        continue
                        
                    normalized_score = res['score'] / max_score if max_score > 0 else 0
                    
                    # Only consider if it's also in our enriched_metas set (double check)
                    if normalized_score >= threshold:
                        duplicates.append(res)
                        total_norm_score += normalized_score
                
                if duplicates:
                    # We found potential matches. 
                    # Group them: Current file + all found duplicates
                    target_ids = [fid] + [d['id'] for d in duplicates]
                    avg_confidence = (total_norm_score + 1.0) / (len(duplicates) + 1)
                    
                    # High confidence (0.90+) -> Auto-merge
                    # Medium confidence (0.75-0.90) -> Validation
                    target_mode = "knowledge_merge" if avg_confidence >= 0.90 else "knowledge_validation"
                    
                    # Sort IDs to ensure stable grouping
                    target_ids = sorted(list(set(target_ids)))
                    
                    # Check if this EXACT group is already being merged
                    group_key = ",".join(target_ids)
                    if any(group_key in p for p in proposals): continue

                    proposal_id = self._create_merge_proposal(
                        target_ids, 
                        title or search_query[:50],
                        confidence=avg_confidence,
                        target=target_mode
                    )
                    if proposal_id:
                        proposals.append(proposal_id)
                        pending_targets.update(target_ids)
                        
            except Exception as e:
                logger.error(f"Error scanning {fid} for duplicates: {e}")
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
            # COORDINATED LOCKING:
            # We switch all target files to 'pending_merge' atomically 
            # to prevent other merge cycles from picking them up.
            with self.memory.semantic.transaction():
                # 1. Create the proposal file
                decision = self.memory.record_decision(
                    title=title,
                    target=target,
                    rationale=rationale,
                    context=ctx_data
                )

                # 2. Lock the source files
                for s_fid in target_ids:
                    self.memory.semantic.update_decision(s_fid, {"status": "pending_merge"}, f"Locked for merge in {decision.metadata.get('file_id')}")

            return decision.metadata.get("file_id")
        except Exception as e:
            logger.error(f"Failed to create merge proposal: {e}")
            return None
