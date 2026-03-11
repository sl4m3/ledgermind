import json
import logging
from typing import List, Dict, Any, Optional
from ..base_service import MemoryService

logger = logging.getLogger("ledgermind.core.api.services.query")

class QueryService(MemoryService):
    """
    Service responsible for searching and retrieving knowledge from memory.
    """
    
    def list_decisions(self) -> List[str]:
        """List all active decision identifiers."""
        return self.semantic.list_decisions()

    def get_decision_history(self, decision_id: str) -> List[Dict[str, Any]]:
        """Retrieve full version history of a specific decision."""
        self.semantic._validate_fid(decision_id)
        return self.semantic.audit.get_history(decision_id)

    def get_recent_events(self, limit: int = 10, include_archived: bool = False) -> List[Dict[str, Any]]:
        """Retrieve recent events from the episodic store."""
        status = None if include_archived else 'active'
        return self.episodic.query(limit=limit, status=status)

    def generate_knowledge_graph(self, target: Optional[str] = None) -> str:
        """Generates a Mermaid graph of knowledge evolution."""
        from ledgermind.core.reasoning.ranking.graph import KnowledgeGraphGenerator
        generator = KnowledgeGraphGenerator(self.semantic.repo_path, self.semantic.meta, self.episodic)
        return generator.generate_mermaid(target_filter=target)

    def search(self, query: str, limit: int = 5, offset: int = 0,
               namespace: Optional[str] = None, mode: str = "balanced") -> List[Dict[str, Any]]:
        """
        Search with Recursive Truth Resolution and Hybrid Vector/Keyword ranking.
        Implementation moved from Memory.search_decisions.
        """
        effective_namespace = namespace or self.context.namespace
        k = 60 # RRF constant        
        # Fast path for simple keyword search (V7.1: Restored heuristic for performance)
        is_short_query = len(query) < 20 and " " not in query.strip()
        if mode == "lite" or (is_short_query and mode == "balanced"):
            search_status = "active" if mode == "strict" else None
            kw_results = self.semantic.meta.keyword_search(query, limit=limit, namespace=effective_namespace, status=search_status)
            if kw_results:
                fast_results = [{
                    "id": r['fid'],
                    "title": r['title'],
                    "preview": r['title'],
                    "target": r['target'],
                    "status": r['status'],
                    "score": 1.0 * self._get_lifecycle_weight(r), # Apply weights
                    "kind": r['kind']
                } for r in kw_results]
                # V7.1: MUST SORT by score, otherwise weights have no effect on order
                return sorted(fast_results, key=lambda x: x['score'], reverse=True)

        search_limit = max(200, (offset + limit) * 10) if namespace else (offset + limit) * 3
        
        vec_results = []
        try:
            vec_results = self.vector.search(query, limit=search_limit)
        except Exception: pass
            
        kw_results = self.semantic.meta.keyword_search(query, limit=search_limit, namespace=effective_namespace)
    
        all_initial_fids = list(set([item.get('id') for item in vec_results] + [r.get('fid') for r in kw_results]))
        meta_cache = {m['fid']: m for m in self.semantic.meta.get_batch_by_fids(all_initial_fids)}

        scores = {}
        for rank, item in enumerate(vec_results):
            fid = item['id']
            meta = meta_cache.get(fid)
            weight = self._get_lifecycle_weight(meta)
            scores[fid] = scores.get(fid, 0.0) + (weight / (k + rank + 1))
            
        for rank, r in enumerate(kw_results):
            fid = r['fid']
            meta = meta_cache.get(fid)
            weight = self._get_lifecycle_weight(meta)
            scores[fid] = scores.get(fid, 0.0) + (weight / (k + rank + 1))

        max_rrf = 3.0 / (k + 1.0)
        sorted_fids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        candidates_meta = self.semantic.meta.get_batch_by_fids(sorted_fids)
        request_cache = {m['fid']: m for m in candidates_meta}

        current_layer_ids = [m['superseded_by'] for m in candidates_meta if m.get('superseded_by')]
        current_layer_ids = [fid for fid in current_layer_ids if fid and fid not in request_cache]

        iteration = 0
        while current_layer_ids and iteration < 5:
            new_batch = self.semantic.meta.get_batch_by_fids(current_layer_ids)
            for m in new_batch:
                request_cache[m['fid']] = m
            current_layer_ids = [m['superseded_by'] for m in new_batch if m.get('superseded_by')]
            current_layer_ids = [fid for fid in current_layer_ids if fid and fid not in request_cache]
            iteration += 1

        resolved_records = []
        for fid in sorted_fids:
            meta = self._resolve_to_truth(fid, mode, cache=request_cache)
            if not meta: continue
            if meta.get('namespace', 'default') != effective_namespace: continue

            status = meta.get("status", "unknown")
            if status in ("processed", "knowledge_merge", "knowledge_validation", "accepted"):
                continue

            if not self.context.include_history and status not in ("active", "superseded", "deprecated", "pending_merge", "draft"):
                if mode != "maintenance" or status != "draft": continue
            
            if mode == "strict" and status not in ("active", "pending_merge"): continue
            # V7.0: Allow draft proposals in balanced mode if they are the latest truth
            # if mode == "balanced" and status == "draft": continue

            resolved_records.append((fid, meta, scores[fid] / max_rrf))

        unique_final_ids = list(set([r[1]['fid'] for r in resolved_records]))
        link_counts = self.episodic.count_links_for_semantic_batch(unique_final_ids)

        final_candidates = {}
        for fid, meta, match_score in resolved_records:
            final_id = meta['fid']
            if final_id in final_candidates:
                final_candidates[final_id]['base_score'] += match_score
                continue

            link_count, _ = link_counts.get(final_id, (0, 0.0))
            boost = min(link_count * 0.2, 1.0) 
            
            phase = meta.get('phase', 'pattern').lower()
            vitality = meta.get('vitality', 'active').lower()
            kind = meta.get('kind', 'proposal').lower()
            
            lifecycle_multiplier = self._get_lifecycle_multiplier(phase, vitality, kind, meta.get("status"))
            
            final_candidates[final_id] = {
                "id": final_id,
                "fid": final_id,
                "base_score": match_score,
                "boost": boost,
                "lifecycle_multiplier": lifecycle_multiplier,
                "status": meta.get("status", "unknown"),
                "title": meta.get("title", "unknown"),
                "preview": meta.get("title", "unknown"),
                "target": meta.get("target", "unknown"),
                "content": meta.get("content", ""),
                "keywords": meta.get("keywords", ""),
                "context_json": meta.get('context_json', '{}'),
                "kind": meta.get("kind"),
                "is_active": (meta.get("status") == "active"),
                "evidence_count": link_count,
                "vitality": vitality,
                "phase": phase
            }

        all_candidates = []
        for cand in final_candidates.values():
            raw_score = (cand['base_score'] + cand['boost']) * cand['lifecycle_multiplier']
            cand['score'] = min(1.0, raw_score)
            all_candidates.append(cand)

        all_candidates.sort(key=lambda x: x['score'], reverse=True)
        final_results = []
        seen_ids = set()
        skipped = 0
        
        for cand in all_candidates:
            if cand['id'] in seen_ids: continue
            if skipped < offset:
                skipped += 1
                continue
            
            try:
                ctx = json.loads(cand.pop('context_json'))
            except Exception: ctx = {}
            
            cand["rationale"] = ctx.get("rationale")
            cand["consequences"] = ctx.get("consequences", [])
            cand["compressive_rationale"] = ctx.get("compressive_rationale")
            cand["strengths"] = ctx.get("strengths", [])
            cand["objections"] = ctx.get("objections", [])
            
            evidence_count = ctx.get("total_evidence_count", 0)
            if evidence_count > 0:
                import math
                reliability_boost = min(0.2, math.log10(evidence_count + 1) * 0.05)
                cand["base_score"] = cand.get("base_score", 0.0) + reliability_boost

            cand["similarity_score"] = min(1.0, cand.get("base_score", 0.0))
            final_results.append(cand)
            seen_ids.add(cand['id'])
            try: self.semantic.meta.increment_hit(cand['id'])
            except Exception: pass
            
            if len(final_results) >= limit: break
            
        return final_results

    def _resolve_to_truth(self, doc_id: str, mode: str, cache: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """Recursively follows 'superseded_by' links."""
        self.semantic._validate_fid(doc_id)
        if mode == "audit":
            if cache and doc_id in cache: return cache[doc_id]
            return self.semantic.meta.get_by_fid(doc_id)

        if cache:
            current_id = doc_id
            depth = 0
            while depth < 20:
                if current_id in cache:
                    meta = cache[current_id]
                    if meta.get("status") == "active" or not meta.get("superseded_by"):
                        return meta
                    current_id = meta.get("superseded_by")
                    depth += 1
                else: break
            else: return None

        return self.semantic.meta.resolve_to_truth(doc_id)

    def _get_lifecycle_weight(self, meta: Optional[Dict[str, Any]]) -> float:
        if not meta: return 1.0
        weight = 1.0
        if meta.get('kind') == 'decision': weight *= 1.35
        phase = (meta.get('phase') or '').lower()
        if phase == 'canonical': weight *= 1.5
        elif phase == 'emergent': weight *= 1.2
        vitality = (meta.get('vitality') or '').lower()
        if vitality == 'decaying': weight *= 0.5
        elif vitality == 'dormant': weight *= 0.2
        return weight

    def _get_lifecycle_multiplier(self, phase: str, vitality: str, kind: str, status: Optional[str]) -> float:
        phase_weights = {"canonical": 1.5, "emergent": 1.2, "pattern": 1.0}
        vitality_weights = {"active": 1.0, "decaying": 0.5, "dormant": 0.2}
        kind_weights = {"decision": 1.35, "proposal": 1.0}
        
        multiplier = (
            phase_weights.get(phase, 1.0) * 
            vitality_weights.get(vitality, 1.0) * 
            kind_weights.get(kind, 1.0)
        )
        if status in ("rejected", "falsified"): multiplier *= 0.2
        elif status in ("superseded", "deprecated"): multiplier *= 0.3
        return multiplier
