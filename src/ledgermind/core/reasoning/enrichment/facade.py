import logging
import os
import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from ledgermind.core.core.schemas import DecisionStream, ProceduralContent, ProceduralStep, DecisionPhase
from ledgermind.core.stores.semantic_store.loader import MemoryLoader
from .clients import CloudLLMClient, LocalLLMClient
from .config import EnrichmentConfig
from .parser import ResponseParser
from .builder import PromptBuilder
from .processor import LogProcessor

logger = logging.getLogger("ledgermind.core.enrichment.facade")

class LLMEnricher:
    """
    Facade for the LLM enrichment subsystem.
    Handles prioritized knowledge processing: Merge -> Validation -> Distillation.
    """
    
    # Пороговые значения для валидации фаз
    MIN_EVIDENCE_FOR_PHASE = {
        DecisionPhase.PATTERN: 0,
        DecisionPhase.EMERGENT: 5,
        DecisionPhase.CANONICAL: 15
    }
    
    MIN_STABILITY_FOR_PHASE = {
        DecisionPhase.PATTERN: 0.0,
        DecisionPhase.EMERGENT: 0.5,
        DecisionPhase.CANONICAL: 0.7
    }
    
    PHASE_ORDER = [DecisionPhase.PATTERN, DecisionPhase.EMERGENT, DecisionPhase.CANONICAL]
    
    def __init__(self, mode: Optional[str] = None, preferred_language: Optional[str] = None):
        self.mode = mode
        self.preferred_language = preferred_language
        self._cloud_client = None
        self._local_client = None
    
    def _inherit_phase_with_validation(
        self,
        source_phases: List[DecisionPhase],
        total_evidence_count: int,
        stability_score: float
    ) -> DecisionPhase:
        """
        Наследует фазу с валидацией по метрикам.
        
        Принцип: максимальная фаза среди исходных, но с проверкой на достаточность метрик.
        Если метрики не дотягивают — фаза понижается до ближайшей подходящей.
        
        Args:
            source_phases: Список фаз исходных гипотез
            total_evidence_count: Суммарное количество evidence
            stability_score: Средняя стабильность
        
        Returns:
            DecisionPhase: Результирующая фаза
        """
        if not source_phases:
            return DecisionPhase.PATTERN
        
        # 1. Определяем максимальную фазу
        max_phase = max(source_phases, key=lambda p: self.PHASE_ORDER.index(p))
        
        # 2. Понижаем фазу если метрики не дотягивают
        for phase in reversed(self.PHASE_ORDER):  # CANONICAL → EMERGENT → PATTERN
            if self.PHASE_ORDER.index(max_phase) >= self.PHASE_ORDER.index(phase):
                min_evidence = self.MIN_EVIDENCE_FOR_PHASE.get(phase, 0)
                min_stability = self.MIN_STABILITY_FOR_PHASE.get(phase, 0.0)
                
                if (total_evidence_count >= min_evidence and 
                    stability_score >= min_stability):
                    return phase
        
        return DecisionPhase.PATTERN

    def run_auto_enrichment(self, memory: Any, limit: Optional[int] = None):
        """Orchestrates prioritized auto-enrichment."""
        # Dynamically determine config if not set
        if memory and hasattr(memory, 'semantic') and hasattr(memory.semantic, 'meta'):
            meta = memory.semantic.meta
            if self.mode is None:
                # Try enrichment_mode, then fallback to arbitration_mode
                self.mode = meta.get_config("enrichment_mode") or meta.get_config("arbitration_mode") or "optimal"
            if self.preferred_language is None:
                self.preferred_language = meta.get_config("preferred_language") or "russian"

        logger.info(f"Auto-Enrichment Triggered: Language={self.preferred_language}, Mode={self.mode}")
        
        # 1. Discover all records where enrichment is still needed
        all_metas = memory.semantic.meta.list_all()
        pending_metas = [m for m in all_metas if m.get('enrichment_status') == 'pending']
        
        if not pending_metas:
            logger.info("No records found with enrichment_status='pending'.")
            return

        # 2. PRIORITY SORTING: Merge -> Validation -> Standard Enrichment
        def get_priority(m):
            target = m.get('target', 'general')
            if target == "knowledge_merge": return 0
            if target == "knowledge_validation": return 1
            return 2

        # Sort by priority first, then by timestamp (ASC - oldest first)
        pending_metas.sort(key=lambda m: (get_priority(m), m.get('timestamp', '')))
        
        if limit: pending_metas = pending_metas[:limit]

        # 3. Process sequentially
        proposals_objs = []
        for m in pending_metas:
            try:
                # Simple object wrapper to satisfy 'getattr' calls
                class ProposalWrapper:
                    def __init__(self, data):
                        self._data = data
                        # Blacklist technical fields from being part of the primary object attributes
                        blacklist = {'context_json', 'content_hash', 'last_hit_at', 'hit_count'}
                        for k, v in data.items(): 
                            if k not in blacklist: setattr(self, k, v)
                        
                        if 'context_json' in data and data['context_json']:
                            try:
                                ctx = json.loads(data['context_json'])
                                for k, v in ctx.items():
                                    if not hasattr(self, k) and k not in blacklist: setattr(self, k, v)
                            except Exception: pass
                    
                    def model_dump(self, mode="json"):
                        # Only include attributes that are not private and not in the protected list
                        dump = {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
                        return dump
                
                proposals_objs.append(ProposalWrapper(m))
            except Exception as e:
                logger.error(f"Failed to load proposal {m.get('fid')}: {e}")

        self.process_batch(proposals_objs, memory.episodic, memory=memory)

    def synthesize_merged_rationale(self, rationales: List[str], memory: Any = None) -> str:
        """
        Synthesizes a unified rationale from multiple source rationales.
        Used during manual proposal acceptance.
        """
        if not rationales:
            return "No rationale provided."
        if len(rationales) == 1:
            return rationales[0]

        logger.info(f"Synthesizing merged rationale for {len(rationales)} items...")
        
        combined_text = "\n\n--- SOURCE RATIONALE ---\n\n".join(rationales)
        config = EnrichmentConfig.from_memory(memory, mode=self.mode or "lite", preferred_language=self.preferred_language or "russian")
        
        # Use existing prompts from builder.py
        instructions = PromptBuilder.build_consolidation_prompt(config)
        full_prompt = PromptBuilder.wrap_with_data(instructions, combined_text, config)
        
        client = self._get_client(config, memory)
        
        try:
            response = client.call("You are a Senior Principal Software Architect.", full_prompt)
            if response:
                res_data = ResponseParser.parse_json(response)
                if res_data and "rationale" in res_data:
                    return str(res_data["rationale"]).strip()
                return response.strip()
        except Exception as e:
            logger.warning(f"LLM Synthesis failed: {e}. Falling back to concatenation.")
            
        return "\n\n".join(rationales)

    def process_batch(self, proposals: List[Any], episodic_store: Any, memory: Any = None) -> List[Any]:
        """Iteratively processes a list of proposals, handling validation clusters separately.

        Operations are split into individual transactions to avoid long-held locks:
        - Validation/Consolidation: Single transaction (fast)
        - Standard enrichment: Per-proposal transactions (LLM calls outside tx)
        """
        results = []
        total = len(proposals)
        processed_count = 0
        error_count = 0

        logger.info(f"Starting enrichment batch with {total} proposals")

        for i, prop in enumerate(proposals, 1):
            try:
                fid = getattr(prop, 'fid', 'unknown')

                # STAGE 1: Handle Knowledge Clusters (Merge & Validation)
                target = getattr(prop, 'target', '')
                target_ids = getattr(prop, 'target_ids', [])

                if target == 'knowledge_validation':
                    status = getattr(prop, 'status', 'unknown')
                    logger.info(f"\n>>> [STEP 1/2: CLUSTER VALIDATION {i}/{total}] Processing {fid} (status={status})")
                    # V7.6: Keep validation in single transaction (fast operation)
                    with memory.semantic.transaction():
                        self._handle_validation_cluster(prop, memory)
                        # V7.5: Mark validation cluster as completed
                        memory.semantic.update_decision(fid, {"enrichment_status": "completed"},
                                                         commit_msg="Enrichment: validation completed")
                    results.append(prop)
                    processed_count += 1
                    continue

                if target == 'knowledge_merge' or target_ids:
                    status = getattr(prop, 'status', 'unknown')
                    logger.info(f"\n>>> [STEP 2/2: DEEP CONSOLIDATION {i}/{total}] Processing {fid} (status={status})")
                    # V7.6: Keep consolidation in single transaction (fast operation)
                    with memory.semantic.transaction():
                        self._execute_consolidation(target_ids, memory, fid)
                    results.append(prop)
                    processed_count += 1
                    continue

                status = getattr(prop, 'status', 'unknown')
                logger.info(f"\n>>> [STEP 3: STANDARD ENRICHMENT {i}/{total}] Processing {fid} (status={status})")

                # V7.6: Standard enrichment with per-proposal transactions
                result = self._process_single_proposal(prop, episodic_store, memory, i, total)
                results.append(result)
                processed_count += 1

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to process {fid}: {e}")
                # Continue with next proposal - don't break entire batch
                continue

        logger.info(f"Batch processing completed: {processed_count}/{total} successful, {error_count} errors")
        return results

    def _process_single_proposal(self, prop: Any, episodic_store: Any, memory: Any, index: int, total: int) -> Any:
        """
        Process a single proposal with per-iteration transactions.
        
        LLM calls happen OUTSIDE transactions to avoid long-held locks.
        Updates happen in SHORT transactions.
        """
        fid = getattr(prop, 'fid', 'unknown')
        current_obj = prop
        iteration = 1
        config = EnrichmentConfig.from_memory(memory, mode=self.mode, preferred_language=self.preferred_language)

        while True:
            eids = getattr(current_obj, 'evidence_event_ids', [])
            if not eids:
                # V7.5: Nothing to enrich, mark as completed
                with memory.semantic.transaction():
                    memory.semantic.update_decision(fid, {"enrichment_status": "completed"}, 
                                                   commit_msg="Enrichment: completed (no evidence)")
                break

            logs_text, used_ids, missing_ids = LogProcessor.get_batch_logs(current_obj, episodic_store, config)

            if not used_ids and not missing_ids:
                # V7.5: No logs found, nothing more to enrich
                with memory.semantic.transaction():
                    memory.semantic.update_decision(fid, {"enrichment_status": "completed"}, 
                                                   commit_msg="Enrichment: completed (no logs)")
                break

            if not used_ids and missing_ids:
                # Only missing IDs found, clear them out and continue
                current_obj.evidence_event_ids = [eid for eid in eids if eid not in missing_ids]
                with memory.semantic.transaction():
                    memory.semantic.update_decision(fid, {"evidence_event_ids": current_obj.evidence_event_ids}, 
                                                   commit_msg=f"Enrichment: removed missing ids")
                continue

            logger.info(f"  - Calling LLM for distillation (Iter {iteration}, {len(used_ids)} events)...")
            # V7.6: LLM call OUTSIDE transaction to avoid long-held locks
            enriched = self.enrich_proposal(current_obj, cluster_logs=logs_text, memory=memory, used_event_ids=used_ids + missing_ids)

            if not enriched: 
                # Mark as completed if LLM failed
                with memory.semantic.transaction():
                    memory.semantic.update_decision(fid, {"enrichment_status": "completed"}, 
                                                   commit_msg="Enrichment: completed (LLM failed)")
                break

            # Check for progress
            if len(getattr(enriched, 'evidence_event_ids', [])) >= len(eids):
                logger.warning(f"  - No progress in Iter {iteration}. Stopping enrichment for {fid}.")
                # Still mark as completed even if no progress
                with memory.semantic.transaction():
                    memory.semantic.update_decision(fid, {"enrichment_status": "completed"}, 
                                                   commit_msg="Enrichment: completed (no progress)")
                break

            # V7.6: Short transaction for update
            with memory.semantic.transaction():
                memory.semantic.update_decision(fid, enriched.model_dump(mode="json"), 
                                               commit_msg=f"Enrichment: Iter {iteration}")

            current_obj = enriched
            iteration += 1
            if iteration > 10: 
                # Hard safety limit
                with memory.semantic.transaction():
                    memory.semantic.update_decision(fid, {"enrichment_status": "completed"}, 
                                                   commit_msg="Enrichment: completed (iteration limit)")
                break

        # V7.5: Final completion marker (already marked in loops above)
        return current_obj

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
                        kind = meta.get('kind', 'proposal')
                        
                        # V7.6: Decision/Constraint/Assumption always stay active
                        if kind in ('decision', 'constraint', 'assumption'):
                            restore_status = 'active'
                        else:
                            restore_status = meta.get('metadata', {}).get('previous_status', 'draft')
                        
                        logger.info(f"  - Group detected (Unique): {u_fid} (kind={kind}). Restoring to {restore_status}.")

                        # V7.6: Read existing fields from context_json
                        ctx_raw = meta.get('context_json')
                        ctx = json.loads(ctx_raw) if ctx_raw else {}
                        existing_title = ctx.get('title') or meta.get('title')
                        existing_rationale = ctx.get('rationale') or meta.get('rationale')

                        # V7.6: Ensure mandatory fields exist for valid DecisionStream
                        update_data = {
                            "status": restore_status,
                            "merge_status": "idle",
                            "superseded_by": None
                        }

                        # Fill mandatory fields only if truly missing
                        if not existing_title:
                            update_data['title'] = f"Hypothesis: {meta.get('target', 'unknown')}"
                        if not existing_rationale:
                            update_data['rationale'] = f"Unique hypothesis for {meta.get('target', 'unknown')}"
                        if not meta.get('first_seen'):
                            update_data['first_seen'] = meta.get('timestamp', datetime.now().isoformat())
                        if not meta.get('last_seen'):
                            update_data['last_seen'] = meta.get('timestamp', datetime.now().isoformat())

                        memory.semantic.update_decision(u_fid, update_data, f"Restore unique: {restore_status}")
                        self._inherit_cluster_evidence(memory, fid, u_fid, filter_fids=[u_fid])
                        handled_fids.add(u_fid)

            # Safety rollbacks
            for tid in target_ids:
                if tid not in handled_fids:
                    meta = memory.semantic.meta.get_by_fid(tid)
                    if meta:
                        kind = meta.get('kind', 'proposal')

                        # V7.6: Decision/Constraint/Assumption always stay active
                        if kind in ('decision', 'constraint', 'assumption'):
                            restore_status = 'active'
                        else:
                            restore_status = meta.get('metadata', {}).get('previous_status', 'draft')

                        # V7.6: Read existing fields from context_json
                        ctx_raw = meta.get('context_json')
                        ctx = json.loads(ctx_raw) if ctx_raw else {}
                        existing_title = ctx.get('title') or meta.get('title')
                        existing_rationale = ctx.get('rationale') or meta.get('rationale')

                        # V7.6: Ensure mandatory fields exist
                        update_data = {
                            "status": restore_status,
                            "merge_status": "idle",
                            "superseded_by": None
                        }
                        if not existing_title:
                            update_data['title'] = f"Hypothesis: {meta.get('target', 'unknown')}"
                        if not existing_rationale:
                            update_data['rationale'] = f"Unique hypothesis for {meta.get('target', 'unknown')}"
                        if not meta.get('first_seen'):
                            update_data['first_seen'] = meta.get('timestamp', datetime.now().isoformat())
                        if not meta.get('last_seen'):
                            update_data['last_seen'] = meta.get('timestamp', datetime.now().isoformat())

                        memory.semantic.update_decision(tid, update_data, "Safety rollback.")

            memory.semantic.update_decision(fid, {"status": "fulfilled", "enrichment_status": "completed"}, f"Done: {res_data.get('reasoning', 'N/A')}")

        except Exception as e:
            logger.error(f"  - Validation failure: {e}")
            for tid in target_ids:
                meta = memory.semantic.meta.get_by_fid(tid)
                if meta:
                    kind = meta.get('kind', 'proposal')

                    # V7.6: Decision/Constraint/Assumption always stay active
                    if kind in ('decision', 'constraint', 'assumption'):
                        restore_status = 'active'
                    else:
                        restore_status = meta.get('metadata', {}).get('previous_status', 'draft')

                    # V7.6: Read existing fields from context_json
                    ctx_raw = meta.get('context_json')
                    ctx = json.loads(ctx_raw) if ctx_raw else {}
                    existing_title = ctx.get('title') or meta.get('title')
                    existing_rationale = ctx.get('rationale') or meta.get('rationale')

                    # V7.6: Ensure mandatory fields exist
                    update_data = {
                        "status": restore_status,
                        "merge_status": "idle",
                        "superseded_by": None
                    }
                    if not existing_title:
                        update_data['title'] = f"Hypothesis: {meta.get('target', 'unknown')}"
                    if not existing_rationale:
                        update_data['rationale'] = f"Unique hypothesis for {meta.get('target', 'unknown')}"
                    if not meta.get('first_seen'):
                        update_data['first_seen'] = meta.get('timestamp', datetime.now().isoformat())
                    if not meta.get('last_seen'):
                        update_data['last_seen'] = meta.get('timestamp', datetime.now().isoformat())

                    memory.semantic.update_decision(tid, update_data, "Error rollback.")
            memory.semantic.update_decision(fid, {"status": "falsified", "enrichment_status": "completed"}, f"Aborted: {str(e)}")

    def _execute_consolidation(self, fids: List[str], memory: Any, parent_fid: str):
        """STEP 2: Consolidation (Architect). Performs deep synthesis."""
        if len(fids) < 2: return
        logger.info(f"  - Starting Deep Architectural Synthesis for {len(fids)} documents...")
        
        docs_full = []
        for fid in fids:
            meta = memory.semantic.meta.get_by_fid(fid)
            if meta:
                full_body = f"FID: {fid}\nTITLE: {meta.get('title')}\nRATIONALE: {meta.get('rationale', '')}\nCONTENT: {meta.get('content', '')}"
                docs_full.append(full_body)
            
        if len(docs_full) < 2: return
        
        docs_summary = "\n\n--- DOCUMENT BOUNDARY ---\n\n".join(docs_full)
        config = EnrichmentConfig.from_memory(memory, mode="rich", preferred_language=self.preferred_language)
        instructions = PromptBuilder.build_consolidation_prompt(config)
        full_prompt = PromptBuilder.wrap_with_data(instructions, docs_summary, config)
        
        logger.info("  - Sending consolidation request to LLM (Heavy Task)...")
        client = self._get_client(config, memory)
        response = client.call("You are a Senior Principal Software Architect.", full_prompt, fid=parent_fid)

        try:
            # Use ResponseParser for robust JSON extraction with escape sequence fixing
            res_data = ResponseParser.parse_json(response)
            if not res_data:
                logger.error(f"LLM response parsing failed. Response length: {len(response)}")
                raise ValueError(f"Failed to parse LLM response. Raw snippet: {response[:300]}...")
            
            logger.debug(f"LLM response parsed successfully. Keys: {list(res_data.keys())}")
            
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

            # Collect metrics from all consolidated proposals for phase inheritance
            source_phases = []
            total_evidence_count = 0
            stability_scores = []

            for g_fid in fids:
                meta = memory.semantic.meta.get_by_fid(g_fid)
                if meta:
                    ctx = json.loads(meta.get('context_json', '{}')) if meta.get('context_json') else {}

                    # Collect phase
                    phase_str = ctx.get('phase', 'pattern')
                    try:
                        source_phases.append(DecisionPhase(phase_str))
                    except ValueError:
                        source_phases.append(DecisionPhase.PATTERN)

                    # Collect evidence count
                    total_evidence_count += ctx.get('total_evidence_count', 0) or meta.get('total_evidence_count', 0)

                    # Collect stability score
                    stability_scores.append(ctx.get('stability_score', 0.0) or meta.get('stability_score', 0.0))

            # Calculate inherited phase with validation
            avg_stability = sum(stability_scores) / len(stability_scores) if stability_scores else 0.0
            inherited_phase = self._inherit_phase_with_validation(
                source_phases=source_phases,
                total_evidence_count=total_evidence_count,
                stability_score=avg_stability
            )

            logger.info(f"  - Inherited phase: {inherited_phase.value} (evidence={total_evidence_count}, stability={avg_stability:.2f})")

            # Create new decision WITH inherited phase (decisions don't have direct event links)
            new_decision = memory.supersede_decision(
                title=title, target=target, rationale=_clean_text(res_data.get("rationale", "Synthesized content.")),
                old_decision_ids=fids, evidence_ids=[], phase=inherited_phase
            )

            new_fid = new_decision.metadata.get('file_id')
            if new_fid:
                # Compute confidence for the consolidated decision
                from ledgermind.core.reasoning.decay import DecayEngine
                decay_engine = DecayEngine()
                computed_confidence = decay_engine.calculate_confidence(
                    total_evidence_count=total_evidence_count,
                    stability_score=avg_stability,
                    hit_count=0  # New decision has no hits yet
                )

                # V7.0: Convert procedural from LLM response (list[dict]) to ProceduralContent
                procedural_raw = res_data.get('procedural')
                procedural_converted = None
                if procedural_raw and isinstance(procedural_raw, list):
                    from ledgermind.core.core.schemas import ProceduralContent, ProceduralStep
                    try:
                        steps = [
                            ProceduralStep(
                                action=_clean_text(step.get('action', '')),
                                expected_outcome=_clean_text(step.get('expected_outcome')),
                                rationale=_clean_text(step.get('rationale'))
                            )
                            for step in procedural_raw
                        ]
                        procedural_converted = ProceduralContent(steps=steps)
                    except Exception as proc_err:
                        logger.warning(f"Failed to convert procedural: {proc_err}")

                updates = {
                    "status": "active",
                    "enrichment_status": "completed",
                    "merge_status": "idle",
                    "keywords": [str(k).strip() for k in res_data.get("keywords", []) if str(k).strip()],
                    "confidence": computed_confidence,
                    "compressive_rationale": _clean_text(res_data.get("compressive_rationale")),
                    "strengths": res_data.get("strengths", []),
                    "objections": res_data.get("objections", []),
                    "consequences": res_data.get("consequences", []),
                    "procedural": procedural_converted.model_dump(mode='json') if procedural_converted else None,
                    "total_evidence_count": total_evidence_count
                }
                memory.semantic.update_decision(new_fid, updates, "Deep architectural consolidation complete.")
                self._inherit_cluster_evidence(memory, parent_fid, new_fid, filter_fids=fids)
                logger.info(f"  - SUCCESS: Created active record: {new_fid} (inherited {total_evidence_count} evidence)")

            if parent_fid != 'unknown':
                meta = memory.semantic.meta.get_by_fid(parent_fid)
                if meta and meta.get('target') in ('knowledge_merge', 'knowledge_validation'):
                    memory.semantic.update_decision(parent_fid, {"status": "fulfilled", "enrichment_status": "completed"}, "Direct consolidation completed.")
                    
        except Exception as e:
            logger.error(f"  - Deep consolidation failed: {e}", exc_info=True)

    def _inherit_cluster_evidence(self, memory: Any, source_fid: str, dest_fid: str, filter_fids: List[str]):
        try:
            event_ids = memory.episodic.get_linked_event_ids(source_fid)
            if not event_ids: return
            events = memory.episodic.get_by_ids(event_ids)
            count = 0
            for ev in events:
                meta = ev.get('metadata')
                if isinstance(meta, str):
                    try: meta = json.loads(meta)
                    except Exception: meta = {}
                intended = (meta or {}).get("intended_fid")
                if not intended or intended in filter_fids:
                    memory.episodic.link_to_semantic(ev.get('id'), dest_fid)
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
        
        def _clean_text(text: Any) -> str:
            if text is None: return ""
            if isinstance(text, (list, tuple)):
                text = " ".join([_clean_text(i) for i in text if i])
            
            text = str(text)
            # Convert literal \n strings to actual newlines
            text = text.replace('\\n', '\n')
            # Normalize line endings and strip trailing whitespace
            lines = [line.rstrip() for line in text.split('\n')]
            return '\n'.join(lines).strip()

        procedural = None
        raw_p = data.get("procedural")
        if raw_p and isinstance(raw_p, list):
            steps = []
            for s in raw_p:
                if not s: continue
                if isinstance(s, dict):
                    steps.append(ProceduralStep(
                        action=_clean_text(s.get("action", "")), 
                        expected_outcome=_clean_text(s.get("expected_outcome")), 
                        rationale=_clean_text(s.get("rationale"))
                    ))
                else:
                    steps.append(ProceduralStep(action=_clean_text(str(s))))
            
            if steps: procedural = ProceduralContent(steps=steps, target_task=getattr(proposal, 'target', ''))
        
        compressive = data.get("compressive") or data.get("compressive_rationale")
        compressive = _clean_text(compressive)
        
        if compressive and memory and hasattr(memory, 'semantic'):
            try:
                full_path = os.path.join(memory.semantic.repo_path, fid)
                rel_path = os.path.relpath(full_path, os.getcwd())
                if "To retrieve more detailed data" not in compressive:
                    compressive = f"{compressive.strip()} To retrieve more detailed data, use cat {rel_path}."
            except Exception: pass
            
        # 3. Evidence Crystallization
        current_eids = getattr(proposal, 'evidence_event_ids', [])
        # Ensure comparison is done with same types (integers)
        processed_set = {int(eid) for eid in (used_ids or [])}
        remaining = [eid for eid in current_eids if int(eid) not in processed_set]
        removed_count = len(current_eids) - len(remaining)
        
        if removed_count > 0:
            logger.info(f"  - Successfully distilled {removed_count} events into the hypothesis.")
        
        total_count = getattr(proposal, 'total_evidence_count', 0) + removed_count
        status = "completed" if not remaining else "pending"

        # V7.0: Compute confidence AFTER all metrics are updated
        from ledgermind.core.reasoning.decay import DecayEngine
        decay_engine = DecayEngine()
        
        stability = getattr(proposal, 'stability_score', 0.0)
        hit_count = getattr(proposal, 'hit_count', 0)
        
        computed_confidence = decay_engine.calculate_confidence(
            total_evidence_count=total_count,
            stability_score=stability,
            hit_count=hit_count
        )

        updates = {
            "title": _clean_text(data.get("title") or data.get("goal") or getattr(proposal, 'title', '')),
            "rationale": _clean_text(data.get("rationale") or getattr(proposal, 'rationale', '')),
            "compressive_rationale": compressive,
            "keywords": ResponseParser.clean_keywords(data.get("keywords", [])),
            "strengths": [_clean_text(s) for s in data.get("strengths", [])],
            "objections": [_clean_text(s) for s in data.get("objections", [])],
            "consequences": [_clean_text(s) for s in data.get("consequences", [])],
            "estimated_utility": float(data.get("estimated_utility", 0.5)),
            "estimated_removal_cost": float(data.get("estimated_removal_cost", 0.5)),
            "procedural": procedural.model_dump(mode="json") if procedural else None,
            "enrichment_status": status,
            "total_evidence_count": total_count,
            "evidence_event_ids": remaining,
            # V7.0: Use computed confidence based on final metrics
            "confidence": computed_confidence,
            "stability_score": stability
        }
        
        # Apply to both __dict__ and internal data for consistency
        for k, v in updates.items(): 
            setattr(proposal, k, v)
            if hasattr(proposal, '_data') and k in proposal._data:
                proposal._data[k] = v
        return proposal
