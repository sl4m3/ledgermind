import logging
import os
import re
import json
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
    Handles prioritized knowledge processing with detailed feedback.
    """
    def __init__(self, mode: str = "optimal", preferred_language: str = "russian"):
        self.mode = mode
        self.preferred_language = preferred_language
        self._cloud_client = None
        self._local_client = None

    def run_auto_enrichment(self, memory: Any, limit: Optional[int] = None):
        """Orchestrates prioritized auto-enrichment."""
        logger.info(f"Auto-Enrichment Triggered: Language={self.preferred_language}, Mode={self.mode}")
        
        all_metas = memory.semantic.meta.list_all()
        pending_metas = [m for m in all_metas if m.get('enrichment_status') == 'pending']
        
        if not pending_metas:
            logger.info("No records found with enrichment_status='pending'.")
            return

        def get_priority(m):
            target = m.get('target', 'general')
            if target == "knowledge_merge": return 0
            if target == "knowledge_validation": return 1
            return 2

        pending_metas.sort(key=get_priority)
        if limit: pending_metas = pending_metas[:limit]
        
        logger.info(f"Queue discovered: {len(pending_metas)} items to process.")

        proposals_objs = []
        for m in pending_metas:
            try:
                class ProposalWrapper:
                    def __init__(self, data):
                        for k, v in data.items(): setattr(self, k, v)
                        if 'context_json' in data and data['context_json']:
                            try:
                                ctx = json.loads(data['context_json'])
                                for k, v in ctx.items():
                                    if not hasattr(self, k): setattr(self, k, v)
                            except Exception: pass
                
                proposals_objs.append(ProposalWrapper(m))
            except Exception as e:
                logger.error(f"Failed to load proposal {m.get('fid')}: {e}")

        self.process_batch(proposals_objs, memory.episodic, memory=memory)

    def process_batch(self, proposals: List[Any], episodic_store: Any, memory: Any = None) -> List[Any]:
        results = []
        total = len(proposals)
        for i, prop in enumerate(proposals, 1):
            fid = getattr(prop, 'fid', 'unknown')
            target = getattr(prop, 'target', '')
            target_ids = getattr(prop, 'target_ids', [])
            
            if target == 'knowledge_validation':
                logger.info(f"\n>>> [STEP 1/2: CLUSTER VALIDATION {i}/{total}] Processing {fid}")
                self._handle_validation_cluster(prop, memory)
                results.append(prop)
                continue
                
            if target == 'knowledge_merge' or target_ids:
                logger.info(f"\n>>> [STEP 2/2: DEEP CONSOLIDATION {i}/{total}] Processing {fid}")
                self._execute_consolidation(target_ids, memory, fid)
                results.append(prop)
                continue

            logger.info(f"\n>>> [STEP 3: STANDARD ENRICHMENT {i}/{total}] Processing {fid}")
            
            current_obj = prop
            iteration = 1
            while True:
                eids = getattr(current_obj, 'evidence_event_ids', [])
                if not eids: break
                events = episodic_store.get_events_by_ids(eids[:50])
                if not events: break
                
                logs_text = "\n".join([f"[{e.timestamp}] {e.content}" for e in events])
                used_ids = [e.id for e in events]

                logger.info(f"  - Calling LLM for distillation (Iter {iteration}, {len(used_ids)} events)...")
                enriched = self.enrich_proposal(current_obj, cluster_logs=logs_text, memory=memory, used_event_ids=used_ids)
                
                if enriched:
                    with memory.semantic.transaction():
                        memory.semantic.update_decision(fid, enriched.model_dump(mode="json"), commit_msg=f"Enrichment: Iter {iteration}")
                current_obj = enriched
                iteration += 1
            results.append(current_obj)
        return results

    def _handle_validation_cluster(self, proposal: Any, memory: Any):
        """STEP 1: Validation (Sorter). Only groups FIDs."""
        target_ids = getattr(proposal, 'target_ids', [])
        fid = getattr(proposal, 'fid', 'unknown')
        if len(target_ids) < 2: return

        logger.info(f"  - Analyzing cluster of {len(target_ids)} items. Searching for semantic boundaries...")
        
        docs_meta = [memory.semantic.meta.get_by_fid(tid) for tid in target_ids if memory.semantic.meta.get_by_fid(tid)]
        if len(docs_meta) < 2: return

        docs_summary = "\n\n".join([f"FID: {d['fid']}\nTitle: {d['title']}\nTarget: {d.get('target', 'unknown')}\nKeywords: {d.get('keywords', [])}\nRationale: {d.get('rationale', '')[:300]}\nContent: {d['content'][:500]}" for d in docs_meta])
        
        config = EnrichmentConfig.from_memory(memory, mode="rich", preferred_language=self.preferred_language)
        instructions = PromptBuilder.build_clustering_prompt(config)
        full_prompt = PromptBuilder.wrap_with_data(instructions, docs_summary, config)
        
        logger.info("  - Sending clustering request to LLM...")
        client = self._get_client(config, memory)
        response = client.call("You are a Duplicate Detection Expert.", full_prompt, fid=fid)
        
        try:
            res_data = json.loads(re.search(r'\{.*\}', response, re.DOTALL).group(0))
            clusters = res_data.get("clusters", [])
            logger.info(f"  - LLM Result: {len(clusters)} groups identified.")
            
            handled_fids = set()
            for group in clusters:
                if not isinstance(group, list) or not group: continue
                group_fids = [f if f.endswith(".md") else f"{f}.md" for f in group]
                
                if len(group_fids) > 1:
                    logger.info(f"  - Group detected (Duplicates): {group_fids}. Passing to CONSOLIDATION.")
                    self._execute_consolidation(group_fids, memory, fid)
                    for g_fid in group_fids: handled_fids.add(g_fid)
                else:
                    u_fid = group_fids[0]
                    meta = memory.semantic.meta.get_by_fid(u_fid)
                    if meta:
                        prev_status = meta.get('metadata', {}).get('previous_status', 'draft')
                        logger.info(f"  - Group detected (Unique): {u_fid}. Restoring to {prev_status}.")
                        memory.semantic.update_decision(u_fid, {"status": prev_status, "merge_status": "idle", "superseded_by": None}, f"Rollback unique: {prev_status}")
                        self._inherit_cluster_evidence(memory, fid, u_fid, filter_fids=[u_fid])
                        handled_fids.add(u_fid)

            for tid in target_ids:
                if tid not in handled_fids:
                    meta = memory.semantic.meta.get_by_fid(tid)
                    if meta:
                        prev_status = meta.get('metadata', {}).get('previous_status', 'draft')
                        memory.semantic.update_decision(tid, {"status": prev_status, "merge_status": "idle", "superseded_by": None}, "Safety rollback.")

            memory.semantic.update_decision(fid, {"status": "fulfilled", "enrichment_status": "completed"}, f"Done: {res_data.get('reasoning', 'N/A')}")

        except Exception as e:
            logger.error(f"  - Validation failure: {e}")
            for tid in target_ids:
                meta = memory.semantic.meta.get_by_fid(tid)
                if meta:
                    prev_status = meta.get('metadata', {}).get('previous_status', 'draft')
                    memory.semantic.update_decision(tid, {"status": prev_status, "merge_status": "idle", "superseded_by": None}, "Error rollback.")
            memory.semantic.update_decision(fid, {"status": "falsified", "enrichment_status": "completed"}, f"Aborted: {str(e)}")

    def _execute_consolidation(self, fids: List[str], memory: Any, parent_fid: str):
        """STEP 2: Consolidation (Architect). Performs deep synthesis."""
        if len(fids) < 2: return
        logger.info(f"  - Starting Deep Architectural Synthesis for {len(fids)} documents...")
        
        docs_full = []
        for fid in fids:
            # Use data from meta index - it's most reliable
            meta = memory.semantic.meta.get_by_fid(fid)
            if meta:
                # Combine meta rationale and full content for maximum context
                full_body = f"FID: {fid}\nTITLE: {meta.get('title')}\nRATIONALE: {meta.get('rationale', '')}\nCONTENT: {meta.get('content', '')}"
                docs_full.append(full_body)
            else:
                logger.warning(f"  - No meta data found for {fid}. Skipping in synthesis.")
            
        if len(docs_full) < 2:
            logger.error(f"  - Consolidation aborted: Only {len(docs_full)} documents with valid meta found.")
            return
        
        total_chars = sum(len(d) for d in docs_full)
        logger.info(f"  - Sending {total_chars} chars of technical evidence to LLM (Architect Role)...")
        
        docs_summary = "\n\n--- DOCUMENT BOUNDARY ---\n\n".join(docs_full)
        config = EnrichmentConfig.from_memory(memory, mode="rich", preferred_language=self.preferred_language)
        instructions = PromptBuilder.build_consolidation_prompt(config)
        full_prompt = PromptBuilder.wrap_with_data(instructions, docs_summary, config)
        
        logger.info("  - Sending consolidation request to LLM (Heavy Task)...")
        client = self._get_client(config, memory)
        response = client.call("You are a Senior Principal Software Architect.", full_prompt, fid=parent_fid)
        
        try:
            res_data = json.loads(re.search(r'\{.*\}', response, re.DOTALL).group(0))
            
            def _clean_text(text: Any) -> str:
                if not text: return ""
                text = str(text).replace('\\n', '\n')
                lines = [line.rstrip() for line in text.split('\n')]
                return '\n'.join(lines).strip()
            
            title = str(res_data.get("title", "Consolidated Knowledge"))
            target = res_data.get("target", "consolidated")
            if isinstance(target, list): target = target[0] if target else "consolidated"
            target = str(target).strip()
            if len(target) < 3: target = "consolidated"
            
            logger.info(f"  - LLM Synthesis Complete: '{title}'")
            
            all_pending_eids = set()
            for g_fid in fids:
                meta = memory.semantic.meta.get_by_fid(g_fid)
                if meta and meta.get('evidence_event_ids'):
                    all_pending_eids.update(meta.get('evidence_event_ids'))

            new_decision = memory.supersede_decision(
                title=title, target=target, rationale=_clean_text(res_data.get("rationale", "Synthesized content.")),
                old_decision_ids=fids, evidence_ids=list(all_pending_eids)
            )
            
            new_fid = new_decision.metadata.get('file_id')
            if new_fid:
                updates = {
                    "status": "active",
                    "enrichment_status": "completed", 
                    "merge_status": "idle",
                    "keywords": [str(k).strip() for k in res_data.get("keywords", []) if str(k).strip()], 
                    "confidence": 1.0,
                    "compressive_rationale": _clean_text(res_data.get("compressive_rationale")),
                    "strengths": res_data.get("strengths", []),
                    "objections": res_data.get("objections", []),
                    "consequences": res_data.get("consequences", []),
                    "procedural": res_data.get("procedural")
                }
                memory.semantic.update_decision(new_fid, updates, "Deep architectural consolidation complete.")
                self._inherit_cluster_evidence(memory, parent_fid, new_fid, filter_fids=fids)
                logger.info(f"  - SUCCESS: Created active record: {new_fid}")

            if parent_fid != 'unknown':
                meta = memory.semantic.meta.get_by_fid(parent_fid)
                if meta and meta.get('target') == 'knowledge_merge':
                    memory.semantic.update_decision(parent_fid, {"status": "fulfilled", "enrichment_status": "completed"}, "Direct merge completed.")
                    
        except Exception as e:
            logger.error(f"  - Deep consolidation failed: {e}", exc_info=True)

    def _inherit_cluster_evidence(self, memory: Any, source_fid: str, dest_fid: str, filter_fids: List[str]):
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
            if count > 0: logger.debug(f"  - Inherited {count} evidence events.")
        except Exception as e:
            logger.warning(f"  - Failed to inherit evidence: {e}")

    def enrich_proposal(self, proposal: Any, cluster_logs: Optional[str] = None, memory: Any = None, used_event_ids: Optional[List[int]] = None) -> Any:
        fid = getattr(proposal, 'fid', 'unknown')
        target = getattr(proposal, 'target', 'general')
        config = EnrichmentConfig.from_memory(memory, self.mode, self.preferred_language)
        instructions = PromptBuilder.build_system_prompt(target, getattr(proposal, 'rationale', ''), config)
        client = self._get_client(config, memory)
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
        fill_pct = (total_count / (total_count + len(remaining)) * 100) if (total_count + len(remaining)) > 0 else 100.0
        status = "completed" if not remaining else "pending"
        updates = {"title": data.get("title") or data.get("goal") or getattr(proposal, 'title', ''), "rationale": data.get("rationale") or getattr(proposal, 'rationale', ''), "compressive_rationale": compressive, "keywords": ResponseParser.clean_keywords(data.get("keywords", [])), "strengths": data.get("strengths", []), "objections": data.get("objections", []), "consequences": data.get("consequences", []), "estimated_utility": float(data.get("estimated_utility", 0.5)), "estimated_removal_cost": float(data.get("estimated_removal_cost", 0.5)), "procedural": procedural, "enrichment_status": status, "total_evidence_count": total_count, "evidence_event_ids": remaining}
        if hasattr(proposal, "model_copy"): return proposal.model_copy(update=updates)
        for k, v in updates.items(): setattr(proposal, k, v)
        return proposal
