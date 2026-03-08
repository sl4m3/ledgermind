import logging
import json
from typing import List, Optional, Set, Dict, Any, TYPE_CHECKING
from ledgermind.core.core.schemas import DecisionStream, KIND_PROPOSAL

if TYPE_CHECKING:
    from ledgermind.core.api.memory import Memory

logger = logging.getLogger("ledgermind-core.merging")

class MergeEngine:
    """
    Scans for semantically identical knowledge and proposes merges.
    Uses a multi-layered verification system with semantic noise reduction.
    """
    def __init__(self, memory: 'Memory'):
        self.memory = memory

    def _get_active_merge_targets(self) -> Set[str]:
        """Returns a set of decision IDs already locked or pending for a merge."""
        targets = set()
        metas = self.memory.semantic.meta.list_all()
        for m in metas:
            status = m.get('status')
            fid = m.get('fid')
            if status == 'pending_merge':
                targets.add(fid)
            if status == 'draft' and m.get('kind') == KIND_PROPOSAL:
                try:
                    ctx = json.loads(m.get('context_json', '{}'))
                    if m.get('target') in ('knowledge_merge', 'knowledge_validation'):
                        supersedes = ctx.get('suggested_supersedes', [])
                        targets.update(supersedes)
                except: continue
        return targets

    def _calculate_jaccard(self, text1: str, text2: str, target1: str = "", target2: str = "", kw1: str = "", kw2: str = "") -> float:
        """Calculates token-based Jaccard similarity between two documents using title, target, and keywords."""
        if not text1 or not text2: return 0.0
        
        def get_tokens(t, target, kw):
            # Combine all semantic signals into a single fingerprint
            combined = f"{t} {target or ''} {kw or ''}"
            # Tokenization: lower, split by separators
            raw_tokens = combined.lower().replace('/', ' ').replace(':', ' ').replace('_', ' ').replace('-', ' ').replace(',', ' ').split()
            # Filter only empty or whitespace tokens. 
            # We keep single characters because in tech paths they might be versions or IDs (e.g. /v1/, /a/)
            return {tk for tk in raw_tokens if tk.strip()}

        s1 = get_tokens(text1, target1, kw1)
        s2 = get_tokens(text2, target2, kw2)
        
        if not s1 or not s2: return 0.0
        return len(s1.intersection(s2)) / len(s1.union(s2))

    def scan_for_duplicates(self, threshold: float = 0.75) -> List[str]:
        """
        Scans enriched decisions and proposals to create consolidation or disambiguation tasks.
        """
        all_metas = self.memory.semantic.meta.list_all()
        enriched_metas = [
            m for m in all_metas 
            if m.get('status') in ('active', 'draft') and m.get('enrichment_status') == 'completed'
        ]

        logger.info(f"MergeEngine: Found {len(enriched_metas)} enriched candidates for duplication scanning.")

        if not enriched_metas:
            return []

        proposals = []
        pending_targets = self._get_active_merge_targets()

        # --- PHASE A: STRUCTURAL CONFLICT DETECTION (I4 Resolution) ---
        target_groups = {}
        for m in enriched_metas:
            t = m.get('target')
            if not t or m['fid'] in pending_targets: continue
            if t not in target_groups: target_groups[t] = []
            target_groups[t].append(m['fid'])
            
        for target, fids in target_groups.items():
            if len(fids) > 1:
                logger.info(f"Structural Conflict: {len(fids)} active decisions for target '{target}'. Creating disambiguation proposal.")
                proposal_id = self._create_merge_proposal(
                    fids, 
                    target,
                    confidence=0.95,
                    target_mode="knowledge_merge"
                )
                if proposal_id:
                    proposals.append(proposal_id)
                    pending_targets.update(fids)

        # --- PHASE B: SEMANTIC CONSOLIDATION ---
        recent_candidates = sorted(enriched_metas, key=lambda x: x.get('timestamp', ''), reverse=True)[:50]
        
        logger.info(f"Consolidation: Scanning {len(recent_candidates)} recent candidates for semantic duplicates.")
        
        for m in recent_candidates:
            fid = m['fid']
            if fid in pending_targets: continue

            try:
                title = m.get('title') or ""
                content_desc = m.get('content') or ""
                keywords = m.get('keywords') or ""
                source_target = m.get('target') or ""

                search_query = f"{title} {content_desc} {keywords}".strip()
                if not search_query: continue
                
                results = self.memory.search_decisions(search_query, limit=10, mode="maintenance")
                if not results: continue

                self_score = 0
                for r in results:
                    if r['id'] == fid:
                        self_score = r.get('similarity_score', r['score'])
                        break
                
                if self_score < 0.05: continue

                duplicates = []
                total_norm_score = 0

                for res in results:
                    res_fid = res['id']
                    if res_fid == fid or res_fid in pending_targets: continue

                    # 1. RRF Similarity (Discovery)
                    # Use similarity_score (pure RRF) instead of boosted ranking score
                    current_score = res.get('similarity_score', res['score'])
                    rrf_sim = min(1.0, current_score / self_score) if self_score > 0 else 0
                    if rrf_sim < threshold: continue

                    # 2. Architectural Guard: Cross-root merging is forbidden
                    res_target = res.get('target', '')
                    if source_target and res_target:
                        source_root = source_target.split('/')[0]
                        res_root = res_target.split('/')[0]
                        if source_root != res_root: continue

                    # 3. Textual Verification (Jaccard) with Noise Filtering
                    res_title = res.get('title') or ""
                    res_content = res.get('content') or ""
                    res_keywords = res.get('keywords') or ""
                    
                    j_title = self._calculate_jaccard(title, res_title, source_target, res_target, keywords, res_keywords)
                    j_content = self._calculate_jaccard(content_desc[:200], res_content[:200])
                    
                    # Effective Jaccard is the max of title or content overlap
                    jaccard_sim = max(j_title, j_content)
                    
                    # ADAPTIVE WEIGHTING:
                    # If titles are extremely short (e.g. "T1", "T2"), Jaccard is unreliable.
                    # We increase RRF weight in such cases.
                    title_tokens = len(title.split())
                    if title_tokens < 3:
                        final_sim = (rrf_sim * 0.9) + (jaccard_sim * 0.1)
                    else:
                        # GUARD: If RRF claims perfect match (1.0) but titles are drastically different, reject
                        if rrf_sim > 0.9 and jaccard_sim < 0.2:
                            continue
                        final_sim = (rrf_sim * 0.6) + (jaccard_sim * 0.4)

                    if final_sim >= threshold:
                        logger.info(f"  Match: {fid} <-> {res_fid} | Final Sim: {final_sim:.4f} (RRF: {rrf_sim:.2f}, Jac: {jaccard_sim:.2f})")
                        duplicates.append(res)
                        total_norm_score += final_sim
                
                if duplicates:
                    target_ids = sorted(list(set([fid] + [d['id'] for d in duplicates])))
                    avg_confidence = (total_norm_score + 1.0) / (len(duplicates) + 1)
                    target_mode = "knowledge_merge" if avg_confidence >= 0.90 else "knowledge_validation"
                    
                    group_key = ",".join(target_ids)
                    if any(group_key in p for p in proposals): continue

                    # FIXED: use 'target_mode' instead of 'target' keyword
                    proposal_id = self._create_merge_proposal(
                        target_ids, 
                        title or search_query[:50],
                        confidence=avg_confidence,
                        target_mode=target_mode
                    )
                    if proposal_id:
                        logger.info(f"  Created {target_mode} proposal: {proposal_id}")
                        proposals.append(proposal_id)
                        pending_targets.update(target_ids)
                        
            except Exception as e:
                logger.error(f"Error scanning {fid} for duplicates: {e}")
                continue
                
        return proposals

    def _create_merge_proposal(self, target_ids: List[str], topic: str, confidence: float = 0.90, target_mode: str = "knowledge_merge") -> Optional[str]:
        target_ids = sorted(list(set(target_ids))) 
        if len(target_ids) < 2: return None
        
        is_validation = target_mode == "knowledge_validation"
        title = f"{'Validate' if is_validation else 'Consolidate'} Knowledge: {topic[:50]}..."
        
        if is_validation:
            rationale = (
                f"POTENTIAL DUPLICATION: {len(target_ids)} entries found with moderate similarity ({confidence:.2%}).\n\n"
                f"Entries: {', '.join(target_ids)}\n\n"
                f"LLM validation is required to determine if these entries should be merged or kept separate."
            )
        else:
            rationale = (
                f"Detected fragmented knowledge across {len(target_ids)} semantically identical entries.\n\n"
                f"Entries ({', '.join(target_ids)}) represent overlapping patterns related to '{topic}'.\n\n"
                f"Consolidation is necessary to maintain a Single Source of Truth."
            )
        
        from ledgermind.core.core.schemas import MemoryEvent, TrustBoundary
        from datetime import datetime

        # V5.9: Aggregate total evidence count from all source records
        total_ev_count = 0
        for tid in target_ids:
            try:
                meta = self.memory.semantic.meta.get_by_fid(tid)
                if meta: total_ev_count += meta.get('total_evidence_count', 0)
            except Exception: pass

        try:
            with self.memory.semantic.transaction():
                result = self.memory.process_event(
                    source="system",
                    kind="proposal",
                    content=title,
                    context={
                        "title": title,
                        "target": target_mode,
                        "status": "draft",
                        "rationale": rationale,
                        "confidence": round(min(1.0, confidence), 4),
                        "suggested_supersedes": target_ids,
                        "enrichment_status": "pending",
                        "total_evidence_count": total_ev_count,
                        "suggested_consequences": ["Original decisions will be superseded and archived"]
                    }
                )
                fid = result.metadata.get("file_id")
                if not fid: raise Exception("Failed to process and save proposal event")
                for s_fid in target_ids:
                    self.memory.semantic.update_decision(s_fid, {"status": "pending_merge"}, f"Locked for merge in {fid}")
            return fid
        except Exception as e:
            logger.error(f"Failed to create merge proposal: {e}")
            return None
