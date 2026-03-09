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
        """Iteratively processes a list of proposals."""
        results = []
        total = len(proposals)
        for i, prop in enumerate(proposals, 1):
            fid = getattr(prop, 'fid', 'unknown')
            logger.info(f"\n>>> [PROPOSAL {i}/{total}: {fid}]")
            
            current_obj = prop
            iteration = 1
            while len(current_obj.evidence_event_ids) > 0:
                config = EnrichmentConfig.from_memory(memory, self.mode, self.preferred_language)
                logs, used_ids = LogProcessor.get_batch_logs(current_obj, episodic_store, config)
                
                if not used_ids: break

                enriched = self.enrich_proposal(current_obj, cluster_logs=logs, memory=memory, used_event_ids=used_ids)
                
                if len(enriched.evidence_event_ids) < len(current_obj.evidence_event_ids):
                    if memory:
                        with memory.semantic.transaction():
                            memory.semantic.update_decision(
                                fid, enriched.model_dump(mode="json", exclude_none=True), 
                                commit_msg=f"Enrichment: Iter {iteration} for {fid}"
                            )
                    current_obj = enriched
                    iteration += 1
                else: break
            results.append(current_obj)
        return results

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
        
        # Increment historical count
        total_count = getattr(proposal, 'total_evidence_count', 0) + removed_count
        
        # Completion status
        total_ev = total_count + len(remaining)
        fill_pct = (total_count / total_ev * 100) if total_ev > 0 else 0.0
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
