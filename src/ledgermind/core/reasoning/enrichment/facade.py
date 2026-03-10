import logging
import os
import re
from typing import List, Dict, Any, Optional

from ledgermind.core.core.schemas import DecisionStream, ProceduralContent, ProceduralStep
from ledgermind.core.stores.semantic_store.loader import MemoryLoader
from .clients import CloudLLMClient, LocalLLMClient
from .config import EnrichmentConfig
from .parser import ResponseParser
from .builder import PromptBuilder

logger = logging.getLogger("ledgermind.core.enrichment.facade")

class LLMEnricher:
    """
    Facade for the LLM enrichment subsystem.
    Handles semantic analysis, knowledge distillation, and duplicate validation.
    """
    def __init__(self, mode: str = "optimal", preferred_language: str = "russian"):
        self.mode = mode
        self.preferred_language = preferred_language
        self._cloud_client = None
        self._local_client = None

    def run_auto_enrichment(self, memory: Any, limit: Optional[int] = None):
        """Discovers pending proposals and enriches them sequentially."""
        logger.info(f"Auto-Enrichment Triggered: Language={self.preferred_language}, Mode={self.mode} (Limit={limit})")
        
        # Discover all pending proposals
        all_proposals = memory.semantic.meta.list_all()
        pending = [p for p in all_proposals if p.get('status') == 'pending'][:limit]
        
        if not pending:
            logger.info("No pending proposals found for enrichment.")
            return

        # Simple object wrapper to satisfy 'getattr' calls in process_batch
        class ProposalWrapper:
            def __init__(self, data):
                for k, v in data.items(): setattr(self, k, v)
                if 'context_json' in data:
                    import json
                    ctx = json.loads(data['context_json'])
                    for k, v in ctx.items(): 
                        if not hasattr(self, k): setattr(self, k, v)

        proposals_objs = [ProposalWrapper(p) for p in pending]

        # Process in batch
        self.process_batch(proposals_objs, memory.episodic, memory=memory)

    def process_batch(self, proposals: List[Any], episodic_store: Any, memory: Any = None) -> List[Any]:
        """Iteratively processes a list of proposals, handling validation clusters separately."""
        results = []
        total = len(proposals)
        for i, prop in enumerate(proposals, 1):
            fid = getattr(prop, 'fid', 'unknown')
            
            # STAGE 2: Handle Knowledge Clusters (Merge & Validation)
            target = getattr(prop, 'target', '')
            target_ids = getattr(prop, 'target_ids', [])
            
            # Using reliable 'target' field as primary indicator
            if target in ('knowledge_merge', 'knowledge_validation') or target_ids:
                logger.info(f"\n>>> [CLUSTER VALIDATION {i}/{total}: {fid}]")
                self._handle_validation_cluster(prop, memory)
                results.append(prop)
                continue

            logger.info(f"\n>>> [PROPOSAL {i}/{total}: {fid}]")
            
            # Normal enrichment flow for standard proposals
            current_obj = prop
            iteration = 1
            while True:
                # 1. Fetch relevant logs for this hypothesis
                eids = getattr(current_obj, 'evidence_event_ids', [])
                if not eids: break
                
                # Fetch limited batch of logs
                events = episodic_store.get_events_by_ids(eids[:50]) # Batch size 50
                if not events: break
                
                logs_text = "\n".join([f"[{e.timestamp}] {e.content}" for e in events])
                used_ids = [e.id for e in events]

                # 2. Call LLM to enrich
                enriched = self.enrich_proposal(current_obj, cluster_logs=logs_text, memory=memory, used_event_ids=used_ids)
                
                # 3. Update semantic store
                if enriched:
                    with memory.semantic.transaction():
                        memory.semantic.update_decision(fid, enriched.model_dump(mode="json"), commit_msg=f"Enrichment: Iter {iteration}")
                current_obj = enriched
                iteration += 1
            results.append(current_obj)
        return results

    def _handle_validation_cluster(self, proposal: Any, memory: Any):
        """Specially handles validation by asking LLM to group documents into sub-clusters of actual duplicates."""
        target_ids = getattr(proposal, 'target_ids', [])
        if len(target_ids) < 2: return

        fid = getattr(proposal, 'fid', 'unknown')
        logger.info(f"Analyzing multi-document cluster of {len(target_ids)} items for {fid}...")
        
        # Load all documents in the cluster
        docs_meta = []
        for tid in target_ids:
            meta = memory.semantic.meta.get_by_fid(tid)
            if meta: docs_meta.append(meta)
            
        if len(docs_meta) < 2: return

        # 1. Build Data Summary
        docs_summary = "\n\n".join([
            f"FID: {d['fid']}\nTitle: {d['title']}\nTarget: {d.get('target', 'unknown')}\nKeywords: {d.get('keywords', [])}\nContent: {d['content'][:800]}" 
            for d in docs_meta
        ])
        
        # 2. Call LLM through Builder
        config = EnrichmentConfig.from_memory(memory, mode="rich", preferred_language=self.preferred_language)
        
        target_type = getattr(proposal, 'target', 'knowledge_validation')
        if target_type == "knowledge_merge":
            instructions = PromptBuilder.build_consolidation_prompt(config)
        else:
            instructions = PromptBuilder.build_clustering_prompt(config)
            
        full_prompt = PromptBuilder.wrap_with_data(instructions, docs_summary, config)
        
        client = self._get_client(config, memory)
        response = client.call("You are a Knowledge Architect and Duplicate Detection Expert.", full_prompt, fid=fid)
        
        import json
        try:
            # Robust JSON extraction
            res_data = json.loads(re.search(r'\{.*\}', response, re.DOTALL).group(0))
            clusters = res_data.get("clusters", [])
            
            # FORCED CONSOLIDATION for knowledge_merge tasks
            if target_type == "knowledge_merge" and len(clusters) > 1:
                logger.warning(f"LLM tried to split a confirmed knowledge_merge cluster {fid}. Overriding to single cluster.")
                all_fids = []
                for c in clusters: all_fids.extend(c.get("fids", []))
                all_fids = list(set(all_fids) | set(target_ids))
                first = clusters[0]
                clusters = [{
                    "fids": all_fids,
                    "unified_title": first.get("unified_title", "Consolidated Knowledge"),
                    "unified_target": first.get("unified_target", "consolidated"),
                    "unified_rationale": first.get("unified_rationale", "Synthesized from confirmed duplicates."),
                    "keywords": first.get("keywords", [])
                }]

            logger.info(f"LLM suggested {len(clusters)} sub-clusters for {fid}.")
            
            handled_fids = set()
            
            for cluster in clusters:
                if not cluster or not isinstance(cluster, dict): continue
                fids = cluster.get("fids", [])
                if not fids: continue
                
                # A. INSTANT CONSOLIDATION (Merge Cluster > 1)
                if len(fids) > 1:
                    logger.info(f"Performing instant merge for group: {fids}")
                    
                    all_pending_eids = set()
                    for g_fid in fids:
                        meta = memory.semantic.meta.get_by_fid(g_fid)
                        if meta and meta.get('evidence_event_ids'):
                            all_pending_eids.update(meta.get('evidence_event_ids'))

                    # Use synthesized content from LLM
                    title = cluster.get("unified_title", "Consolidated Knowledge")
                    target = cluster.get("unified_target", "consolidated")
                    rationale = cluster.get("unified_rationale", "Synthesized from multiple sources.")
                    keywords = cluster.get("keywords", [])
                    
                    # Execute atomic merge in core (OLD status was active/draft, so this works now!)
                    new_decision = memory.supersede_decision(
                        title=title,
                        target=target,
                        rationale=rationale,
                        old_decision_ids=fids,
                        evidence_ids=list(all_pending_eids)
                    )
                    
                    # Update metadata for the new record
                    memory.semantic.update_decision(new_decision.fid, {
                        "enrichment_status": "completed",
                        "keywords": keywords,
                        "confidence": 1.0,
                        "merge_status": "idle" # Result is free
                    }, commit_msg="Instant consolidation complete.")
                    
                    # REDISTRIBUTION: Inherit episodic evidence by intended_fid
                    self._inherit_cluster_evidence(memory, fid, new_decision.fid, filter_fids=fids)
                    
                    for g_fid in fids: handled_fids.add(g_fid)
                
                # B. UNIQUE ITEM (Group size == 1) - RESET MERGE STATUS
                else:
                    u_fid = fids[0]
                    meta = memory.semantic.meta.get_by_fid(u_fid)
                    if meta:
                        # Just release the reservation, status remains same (draft/active)
                        memory.semantic.update_decision(u_fid, {"merge_status": "idle"}, 
                                                       f"Rollback: Document identified as unique by LLM.")
                        
                        # REDISTRIBUTION: Return evidence back to the unique doc
                        self._inherit_cluster_evidence(memory, fid, u_fid, filter_fids=[u_fid])
                        
                        handled_fids.add(u_fid)
                        logger.info(f"Released reservation for unique document {u_fid}")

            # C. SAFETY: Restore any documents that LLM might have missed
            for tid in target_ids:
                if tid not in handled_fids:
                    meta = memory.semantic.meta.get_by_fid(tid)
                    if meta:
                        memory.semantic.update_decision(tid, {"merge_status": "idle"}, 
                                                       f"Rollback: Safety (Missed by LLM response).")
                        logger.warning(f"Safety release for {tid}")

            # Mark the validation proposal itself as fulfilled
            memory.semantic.update_decision(fid, {"status": "fulfilled", "enrichment_status": "completed"}, 
                                           f"Consolidation complete: {res_data.get('global_reasoning', 'No reasoning provided')}")

        except Exception as e:
            logger.error(f"Failed to process multi-document validation for {fid}: {e}", exc_info=True)
            # Global release for the whole cluster
            for tid in target_ids:
                meta = memory.semantic.meta.get_by_fid(tid)
                if meta:
                    memory.semantic.update_decision(tid, {"merge_status": "idle"}, 
                                                   "Rollback: Validation system error.")
            memory.semantic.update_decision(fid, {"status": "falsified", "enrichment_status": "completed"}, 
                                           f"Consolidation aborted due to error: {str(e)}")

    def _inherit_cluster_evidence(self, memory: Any, source_fid: str, dest_fid: str, filter_fids: List[str]):
        """Moves episodic evidence from one semantic record to another with filtering by intended target."""
        try:
            event_ids = memory.episodic.get_linked_event_ids(source_fid)
            if not event_ids: return
            
            events = memory.episodic.get_events_by_ids(event_ids)
            
            count = 0
            for ev in events:
                intended = ev.metadata.get("intended_fid")
                if not intended or intended in filter_fids:
                    memory.episodic.link_to_semantic(ev.id, dest_fid)
                    count += 1
                    
            if count > 0:
                logger.debug(f"Inherited {count} evidence events from {source_fid} to {dest_fid}")
        except Exception as e:
            logger.warning(f"Failed to inherit evidence: {e}")

    def enrich_proposal(self, proposal: Any, cluster_logs: Optional[str] = None, memory: Any = None, used_event_ids: Optional[List[int]] = None) -> Any:
        fid = getattr(proposal, 'fid', 'unknown')
        target = getattr(proposal, 'target', 'general')
        config = EnrichmentConfig.from_memory(memory, self.mode, self.preferred_language)
        
        instructions = PromptBuilder.build_system_prompt(target, getattr(proposal, 'rationale', ''), config)
        
        client = self._get_client(config, memory)
        response = client.call(instructions, cluster_logs or "", fid=fid)
        
        if not response:
            alt_mode = "rich" if self.mode == "optimal" else "optimal"
            alt_config = EnrichmentConfig.from_memory(memory, alt_mode, self.preferred_language)
            client = self._get_client(alt_config, memory)
            response = client.call(instructions, cluster_logs or "", fid=fid)
            
        if not response: return proposal

        data = ResponseParser.parse_json(response)
        return self._apply_mapping(proposal, data, used_event_ids, memory) if data else proposal

    def _get_client(self, config: EnrichmentConfig, memory: Any):
        if config.mode == "rich":
            if not self._cloud_client: self._cloud_client = CloudLLMClient(config, memory)
            return self._cloud_client
        else:
            if not self._local_client: self._local_client = LocalLLMClient(config, memory)
            return self._local_client

    def _apply_mapping(self, proposal: Any, data: Dict[str, Any], used_ids: Optional[List[int]], memory: Any) -> Any:
        fid = getattr(proposal, 'fid', 'unknown')
        
        procedural = None
        raw_p = data.get("procedural")
        if raw_p and isinstance(raw_p, list):
            steps = [ProceduralStep(action=s["action"], expected_outcome=s.get("expected_outcome"), rationale=s.get("rationale")) 
                    if isinstance(s, dict) else ProceduralStep(action=str(s)) for s in raw_p if s]
            if steps: procedural = ProceduralContent(steps=steps, target_task=getattr(proposal, 'target', ''))

        compressive = data.get("compressive") or data.get("compressive_rationale")
        if compressive and memory and hasattr(memory, 'semantic'):
            try:
                full_path = os.path.join(memory.semantic.repo_path, fid)
                rel_path = os.path.relpath(full_path, os.getcwd())
                compressive = f"{compressive.strip()} To retrieve more detailed data, use cat {rel_path}."
            except Exception: pass

        current_eids = getattr(proposal, 'evidence_event_ids', [])
        used_set = set(used_ids or [])
        remaining = [eid for eid in current_eids if eid not in used_set]
        removed_count = len(current_eids) - len(remaining)
        
        total_count = getattr(proposal, 'total_evidence_count', 0) + removed_count
        total_ev = total_count + len(remaining)
        fill_pct = (total_count / total_ev * 100) if total_ev > 0 else 100.0
        status = "completed" if not remaining else "pending"
        
        logger.info(f"Success: {removed_count} events processed ({fill_pct:.1f}% knowledge distilled) for {fid}")

        updates = {
            "title": data.get("title") or data.get("goal") or getattr(proposal, 'title', ''),
            "rationale": data.get("rationale") or getattr(proposal, 'rationale', ''),
            "compressive_rationale": compressive,
            "keywords": ResponseParser.clean_keywords(data.get("keywords", [])),
            "strengths": data.get("strengths", []),
            "objections": data.get("objections", []),
            "consequences": data.get("consequences", []),
            "estimated_utility": float(data.get("estimated_utility", 0.5)),
            "estimated_removal_cost": float(data.get("estimated_removal_cost", 0.5)),
            "procedural": procedural,
            "enrichment_status": status,
            "total_evidence_count": total_count,
            "evidence_event_ids": remaining
        }
        
        if hasattr(proposal, "model_copy"):
            return proposal.model_copy(update=updates)
        for k, v in updates.items(): setattr(proposal, k, v)
        return proposal
