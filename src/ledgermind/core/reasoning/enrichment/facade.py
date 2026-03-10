import logging
import os
import re
from typing import List, Dict, Any, Optional

from ledgermind.core.core.schemas import DecisionStream, ProceduralContent, ProceduralStep
from ledgermind.core.stores.semantic_store.loader import MemoryLoader
from .config import EnrichmentConfig
from .processor import LogProcessor
from .builder import PromptBuilder
from .parser import ResponseParser
from .clients import CloudLLMClient, LocalLLMClient

logger = logging.getLogger("ledgermind-core.enrichment")

class LLMEnricher:
    """
    Facade for knowledge enrichment using specialized components.
    """
    def __init__(self, mode: Optional[str] = None, preferred_language: Optional[str] = None):
        self.mode = mode
        self.preferred_language = preferred_language
        self._cloud_client = None
        self._local_client = None

    def run_auto_enrichment(self, memory: Any, limit: Optional[int] = None):
        """
        High-level orchestration:
        1. Audits existing records for language consistency.
        2. Discovers pending proposals.
        3. Executes iterative enrichment (optionally limited to N items).
        """
        # 1. Resolve configuration
        mode = self.mode or memory.semantic.meta.get_config("arbitration_mode") or "rich"
        lang = self.preferred_language or memory.semantic.meta.get_config("preferred_language") or "russian"
        self.mode = mode
        self.preferred_language = lang
        
        logger.info(f"Auto-Enrichment Triggered: Language={lang}, Mode={mode} (Limit={limit or 'None'})")

        # 2. Language Audit
        if lang == "russian":
            self._audit_language_consistency(memory)

        # 3. Discovery
        all_metas = memory.semantic.meta.list_all()
        pending_metas = [m for m in all_metas if m.get('enrichment_status') == 'pending']
        pending_metas.sort(key=lambda x: x.get('fid', '')) # Sequential ordering
        
        if limit:
            pending_metas = pending_metas[:limit]
            
        if not pending_metas:
            logger.info("No pending enrichment work found.")
            return

        # 4. Loading
        proposals = []
        for m in pending_metas:
            try:
                file_path = os.path.join(memory.semantic.repo_path, m['fid'])
                with open(file_path, 'r', encoding='utf-8') as f:
                    data, _ = MemoryLoader.parse(f.read())
                    obj = DecisionStream(**data.get('context', {}))
                    obj.fid = m['fid']
                    proposals.append(obj)
            except Exception as e:
                logger.warning(f"Failed to load {m['fid']} for enrichment: {e}")

        # 5. Process
        if proposals:
            self.process_batch(proposals, memory.episodic, memory=memory)

    def _audit_language_consistency(self, memory: Any):
        """Resets enrichment status if record rationale lacks target language (Cyrillic)."""
        logger.info("Running language consistency audit...")
        all_metas = memory.semantic.meta.list_all()
        to_repair = []
        
        for m in all_metas:
            fid = m['fid']
            try:
                file_path = os.path.join(memory.semantic.repo_path, fid)
                with open(file_path, 'r', encoding='utf-8') as f:
                    data, _ = MemoryLoader.parse(f.read())
                    text = (data.get('context', {}).get('rationale', '') or "").lower()
                    # If non-empty rationale has no cyrillic
                    if text.strip() and not re.search(r'[а-яё]', text):
                        to_repair.append(fid)
            except Exception: continue

        if to_repair:
            logger.info(f"Audit: Found {len(to_repair)} English-only records. Queuing for re-enrichment.")
            with memory.semantic.transaction():
                for fid in to_repair:
                    memory.semantic.update_decision(fid, {"enrichment_status": "pending"}, "Audit: Language mismatch.")

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
            current_obj = prop
            iteration = 1
            while len(current_obj.evidence_event_ids) > 0:
                # ... existing enrichment logic ...
                config = EnrichmentConfig.from_memory(memory, self.mode, self.preferred_language)
                logs, used_ids, missing_ids = LogProcessor.get_batch_logs(current_obj, episodic_store, config)
                
                if not used_ids and not missing_ids:
                    break

                enriched = self.enrich_proposal(current_obj, cluster_logs=logs, memory=memory, used_event_ids=used_ids)
                # ... update and continue ...
                if memory:
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
        instructions = PromptBuilder.build_clustering_prompt(config)
        full_prompt = PromptBuilder.wrap_with_data(instructions, docs_summary, config)
        
        client = self._get_client(config, memory)
        response = client.call("You are a Duplicate Detection Expert.", full_prompt, fid=fid)
        
        import json
        try:
            # Robust JSON extraction
            res_data = json.loads(re.search(r'\{.*\}', response, re.DOTALL).group(0))
            clusters = res_data.get("clusters", [])
            
            logger.info(f"LLM suggested {len(clusters)} sub-clusters for {fid}.")
            
            handled_fids = set()
            
            with memory.semantic.transaction():
                for group in clusters:
                    if not group or not isinstance(group, list): continue
                    
                    # A. ACTUAL MERGE (Group size > 1)
                    if len(group) > 1:
                        # Extract titles for the new merged knowledge
                        first_doc = memory.semantic.meta.get_by_fid(group[0])
                        title = first_doc['title'] if first_doc else "Merged Knowledge Cluster"
                        
                        from ledgermind.core.core.schemas import MemoryEvent, KIND_PROPOSAL
                        from datetime import datetime
                        merge_event = MemoryEvent(
                            source="system",
                            kind=KIND_PROPOSAL,
                            content=f"Merge Confirmed: {title}",
                            timestamp=datetime.now(),
                            context={
                                "topic": f"Merge Cluster (LLM Confirmed)",
                                "target_ids": group,
                                "supersedes": group, # Backlink compatibility
                                "confidence": 1.0,
                                "status": "pending",
                                "target": "knowledge_merge"
                            }
                        )
                        new_merge_fid = memory.semantic.save(merge_event)
                        
                        # REDISTRIBUTION: Inherit evidence from the validation cluster to this specific merge
                        self._inherit_cluster_evidence(memory, fid, new_merge_fid)
                        
                        for g_fid in group: handled_fids.add(g_fid)
                        logger.info(f"Created confirmed merge {new_merge_fid} for group: {group}")
                    
                    # B. UNIQUE ITEM (Group size == 1) - ROLLBACK
                    else:
                        u_fid = group[0]
                        meta = memory.semantic.meta.get_by_fid(u_fid)
                        if meta:
                            prev_status = meta.get('metadata', {}).get('previous_status', 'draft')
                            memory.semantic.update_decision(u_fid, {"status": prev_status, "superseded_by": None}, 
                                                           f"Rollback: Document identified as unique by LLM.")
                            
                            # REDISTRIBUTION: Return evidence back to the unique doc from the validation cluster
                            self._inherit_cluster_evidence(memory, fid, u_fid)
                            
                            handled_fids.add(u_fid)
                            logger.info(f"Restored unique document {u_fid} to {prev_status}")

    def _inherit_cluster_evidence(self, memory: Any, source_fid: str, dest_fid: str):
        """Moves episodic evidence from one semantic record to another."""
        try:
            # Get all event IDs linked to the source (validation cluster)
            event_ids = memory.episodic.get_linked_event_ids(source_fid)
            if not event_ids: return
            
            # Transfer links in episodic store
            for eid in event_ids:
                memory.episodic.link_to_semantic(eid, dest_fid)
            logger.debug(f"Inherited {len(event_ids)} evidence events from {source_fid} to {dest_fid}")
        except Exception as e:
            logger.warning(f"Failed to inherit evidence: {e}")

                # C. SAFETY: Restore any documents that LLM might have missed in the JSON response
                for tid in target_ids:
                    if tid not in handled_fids:
                        meta = memory.semantic.meta.get_by_fid(tid)
                        if meta:
                            prev_status = meta.get('metadata', {}).get('previous_status', 'draft')
                            memory.semantic.update_decision(tid, {"status": prev_status, "superseded_by": None}, 
                                                           "Rollback: Safety (Missed by LLM clustering).")
                            logger.warning(f"Safety rollback for {tid} (missed by LLM response)")

                # Mark the validation proposal itself as fulfilled
                memory.semantic.update_decision(fid, {"status": "fulfilled", "enrichment_status": "completed"}, 
                                               f"Clustering complete: {res_data.get('reasoning', 'No reasoning provided')}")

        except Exception as e:
            logger.error(f"Failed to process multi-document validation for {fid}: {e}")
            # Global rollback for the whole cluster if something went wrong
            with memory.semantic.transaction():
                for tid in target_ids:
                    meta = memory.semantic.meta.get_by_fid(tid)
                    if meta:
                        prev_status = meta.get('metadata', {}).get('previous_status', 'draft')
                        memory.semantic.update_decision(tid, {"status": prev_status, "superseded_by": None}, 
                                                       "Rollback: Validation system error.")
                memory.semantic.update_decision(fid, {"status": "falsified", "enrichment_status": "completed"}, 
                                               f"Clustering aborted due to error: {str(e)}")


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
        
        # 1. Procedural Content
        procedural = None
        raw_p = data.get("procedural")
        if raw_p and isinstance(raw_p, list):
            steps = [ProceduralStep(action=s["action"], expected_outcome=s.get("expected_outcome"), rationale=s.get("rationale")) 
                    if isinstance(s, dict) else ProceduralStep(action=str(s)) for s in raw_p if s]
            if steps: procedural = ProceduralContent(steps=steps, target_task=getattr(proposal, 'target', ''))

        # 2. Compressive + cat suffix
        compressive = data.get("compressive") or data.get("compressive_rationale")
        if compressive and memory and hasattr(memory, 'semantic'):
            try:
                full_path = os.path.join(memory.semantic.repo_path, fid)
                rel_path = os.path.relpath(full_path, os.getcwd())
                compressive = f"{compressive.strip()} To retrieve more detailed data, use cat {rel_path}."
            except Exception: pass

        # 3. Evidence Crystallization (Robust logic)
        current_eids = getattr(proposal, 'evidence_event_ids', [])
        used_set = set(used_ids or [])
        
        # New queue: only those that were NOT in the used set
        remaining = [eid for eid in current_eids if eid not in used_set]
        
        # How many did we actually remove this time?
        removed_count = len(current_eids) - len(remaining)
        
        if removed_count == 0 and used_ids:
            logger.warning(f"Events were provided but not removed from queue for {fid}. Check logic!")

        # Increment historical count
        total_count = getattr(proposal, 'total_evidence_count', 0) + removed_count
        
        # Completion status
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
