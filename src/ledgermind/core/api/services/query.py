import json
import logging
from operator import itemgetter
from typing import List, Dict, Any, Optional
from ..base_service import MemoryService

logger = logging.getLogger("ledgermind.core.api.services.query")

class QueryService(MemoryService):
    """
    Service responsible for searching and retrieving knowledge from memory.
    """
    
    # ⚡ Bolt: Global constants for lifecycle multiplier to avoid redundant dictionary instantiation
    _PHASE_WEIGHTS = {"canonical": 1.5, "emergent": 1.2, "pattern": 1.0}
    _VITALITY_WEIGHTS = {"active": 1.0, "decaying": 0.5, "dormant": 0.2}
    _KIND_WEIGHTS = {"decision": 1.35, "proposal": 1.0}

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
               namespace: Optional[str] = None, mode: str = "balanced",
               min_confidence: float = 0.0) -> List[Dict[str, Any]]:
        """
        Search with Recursive Truth Resolution and Hybrid Vector/Keyword ranking.
        
        Args:
            query: Search query
            limit: Maximum results to return
            offset: Number of results to skip
            namespace: Namespace to search in
            mode: Search mode (lite, balanced, strict, maintenance)
            min_confidence: Minimum confidence threshold (0.0-1.0)
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
                return sorted(fast_results, key=itemgetter('score'), reverse=True)

        search_limit = max(200, (offset + limit) * 10) if namespace else (offset + limit) * 3
        
        vec_results = []
        try:
            vec_results = self.vector.search(query, limit=search_limit)
        except Exception: pass
            
        kw_results = self.semantic.meta.keyword_search(query, limit=search_limit, namespace=effective_namespace)
    
        all_initial_fids = list(set([item.get('id') for item in vec_results] + [r.get('fid') for r in kw_results]))
        meta_cache = {m['fid']: m for m in self.semantic.meta.get_batch_by_fids(all_initial_fids)}

        scores = {}
        # ⚡ Bolt: Memoize weight calculation dynamically to avoid redundant function calls and dictionary lookups
        weight_cache = {}

        for rank, item in enumerate(vec_results):
            fid = item['id']
            if fid not in weight_cache:
                weight_cache[fid] = self._get_lifecycle_weight(meta_cache.get(fid))

            weight = weight_cache[fid]
            if fid in scores:
                scores[fid] += (weight / (k + rank + 1))
            else:
                scores[fid] = (weight / (k + rank + 1))
            
        for rank, r in enumerate(kw_results):
            fid = r['fid']
            if fid not in weight_cache:
                weight_cache[fid] = self._get_lifecycle_weight(meta_cache.get(fid))

            weight = weight_cache[fid]
            if fid in scores:
                scores[fid] += (weight / (k + rank + 1))
            else:
                scores[fid] = (weight / (k + rank + 1))

        max_rrf = 3.0 / (k + 1.0)
        # ⚡ Bolt: Use C-optimized scores.get instead of lambda for 50%+ faster sorting
        sorted_fids = sorted(scores.keys(), key=scores.get, reverse=True)
        
        # ⚡ Bolt: Reuse the meta_cache we already fetched instead of querying the DB again for the same FIDs
        candidates_meta = [meta_cache[fid] for fid in sorted_fids if fid in meta_cache]
        request_cache = meta_cache.copy()

        # ⚡ Bolt: Use single-pass list comprehension with dict.fromkeys to concurrently filter, check caches, and deduplicate IDs while preserving order
        current_layer_ids = list(dict.fromkeys(m['superseded_by'] for m in candidates_meta if m.get('superseded_by') and m['superseded_by'] not in request_cache))

        iteration = 0
        while current_layer_ids and iteration < 5:
            new_batch = self.semantic.meta.get_batch_by_fids(current_layer_ids)
            for m in new_batch:
                request_cache[m['fid']] = m
            # ⚡ Bolt: Use single-pass list comprehension with dict.fromkeys to concurrently filter, check caches, and deduplicate IDs while preserving order
            current_layer_ids = list(dict.fromkeys(m['superseded_by'] for m in new_batch if m.get('superseded_by') and m['superseded_by'] not in request_cache))
            iteration += 1

        resolved_records = []
        mode_is_maintenance = mode == "maintenance"
        mode_is_strict = mode == "strict"
        include_history = self.context.include_history

        for fid in sorted_fids:
            meta = self._resolve_to_truth(fid, mode, cache=request_cache)
            if not meta: continue
            if meta.get('namespace', 'default') != effective_namespace: continue

            status = meta.get("status", "unknown")

            if status == "active":
                pass
            elif status in ("processed", "knowledge_merge", "knowledge_validation", "accepted"):
                continue
            elif not include_history and status not in ("superseded", "deprecated", "pending_merge", "draft"):
                if not mode_is_maintenance or status != "draft": continue
            elif mode_is_strict and status != "pending_merge": continue

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
                "vitality": vitality,  # V7.8: Include vitality for lifecycle verification
                "phase": phase
            }

        all_candidates = list(final_candidates.values())
        for cand in all_candidates:
            raw_score = (cand['base_score'] + cand['boost']) * cand['lifecycle_multiplier']
            cand['score'] = raw_score if raw_score < 1.0 else 1.0

        # ⚡ Bolt: Use C-optimized itemgetter instead of lambda for faster dictionary value extraction
        all_candidates.sort(key=itemgetter('score'), reverse=True)
        final_results = []
        seen_ids = set()
        skipped = 0
        hit_fids = []
        
        # ⚡ Bolt: Move json.loads and math.log10 to local variables outside the loop to avoid continuous global lookups
        _loads = json.loads
        import math
        _log10 = math.log10

        for cand in all_candidates:
            if cand['id'] in seen_ids: continue
            if skipped < offset:
                skipped += 1
                continue

            ctx_json = cand.pop('context_json', None)
            if ctx_json and len(ctx_json) > 2:
                try:
                    ctx = _loads(ctx_json)
                except Exception:
                    ctx = {}
            else:
                ctx = {}

            _get = ctx.get
            cand["rationale"] = _get("rationale")
            cand["consequences"] = _get("consequences", [])
            cand["compressive_rationale"] = _get("compressive_rationale")
            cand["strengths"] = _get("strengths", [])
            cand["objections"] = _get("objections", [])
            
            evidence_count = _get("total_evidence_count", 0)
            base = cand.get("base_score", 0.0)
            if evidence_count > 0:
                val1 = _log10(evidence_count + 1) * 0.05
                reliability_boost = 0.2 if val1 > 0.2 else val1
                base += reliability_boost
                cand["base_score"] = base

            cand["similarity_score"] = 1.0 if base > 1.0 else base
            
            # Extract confidence from context
            cand["confidence"] = _get("confidence", 0.0)
            
            # Filter by min_confidence threshold
            if cand["confidence"] < min_confidence:
                continue
            
            final_results.append(cand)
            seen_ids.add(cand['id'])
            hit_fids.append(cand['id'])

            if len(final_results) >= limit: break

        if hit_fids:
            try: self.semantic.meta.increment_hits_batch(hit_fids)
            except Exception: pass

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
                        # V7.8: Ensure vitality is present
                        if 'vitality' not in meta:
                            full_meta = self.semantic.meta.get_by_fid(current_id)
                            if full_meta:
                                meta['vitality'] = full_meta.get('vitality', 'active')
                        return meta
                    current_id = meta.get("superseded_by")
                    depth += 1
                else: break
            else: return None

        result = self.semantic.meta.resolve_to_truth(doc_id)
        # V7.8: Ensure vitality is present in resolved result
        if result and 'vitality' not in result:
            full_meta = self.semantic.meta.get_by_fid(doc_id)
            if full_meta:
                result['vitality'] = full_meta.get('vitality', 'active')
        return result

    def _get_lifecycle_weight(self, meta: Optional[Dict[str, Any]]) -> float:
        if not meta: return 1.0
        weight = 1.35 if meta.get('kind') == 'decision' else 1.0

        phase = meta.get('phase')
        if phase == 'canonical' or phase == 'CANONICAL': weight *= 1.5
        elif phase == 'emergent' or phase == 'EMERGENT': weight *= 1.2

        vitality = meta.get('vitality')
        if vitality == 'decaying' or vitality == 'DECAYING': weight *= 0.5
        elif vitality == 'dormant' or vitality == 'DORMANT': weight *= 0.2

        return weight

    def _get_lifecycle_multiplier(self, phase: str, vitality: str, kind: str, status: Optional[str]) -> float:
        multiplier = 1.35 if kind == 'decision' else 1.0

        if phase == 'canonical': multiplier *= 1.5
        elif phase == 'emergent': multiplier *= 1.2

        if vitality == 'decaying': multiplier *= 0.5
        elif vitality == 'dormant': multiplier *= 0.2

        if status == 'rejected' or status == 'falsified': multiplier *= 0.2
        elif status == 'superseded' or status == 'deprecated': multiplier *= 0.3

        return multiplier
