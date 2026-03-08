import logging
import os
import json
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from ledgermind.core.core.schemas import (
    MemoryEvent, KIND_PROPOSAL, KIND_DECISION, KIND_RESULT, KIND_ERROR, KIND_INTERVENTION,
    DecisionStream, DecisionPhase, DecisionVitality, PatternScope, ProposalContent
)
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore
from ledgermind.core.reasoning.lifecycle import LifecycleEngine

logger = logging.getLogger(__name__)

class ReflectionPolicy:
    def __init__(self, 
                 error_threshold: int = 1,
                 success_threshold: int = 5,
                 distillation_window_size: int = 1000):
        self.error_threshold = error_threshold
        self.success_threshold = success_threshold
        self.distillation_window_size = distillation_window_size

class ReflectionEngine:
    """
    Analyzes episodic memory to discover behavioral patterns and evolve knowledge.
    """
    def __init__(self, episodic: EpisodicStore, semantic: SemanticStore, processor: Any = None):
        self.episodic = episodic
        self.semantic = semantic
        self.processor = processor
        self.policy = ReflectionPolicy()
        self.lifecycle = LifecycleEngine()
        
        self.BLACKLISTED_TARGETS = {"unknown", "general", "system"}

    def _get_all_streams(self) -> Dict[str, Dict[str, Any]]:
        """Fetch all active/draft semantic entries for cross-referencing."""
        all_metas = self.semantic.meta.list_all()
        return {m['fid']: m for m in all_metas if m.get('status') in ('active', 'draft')}

    def _cluster_evidence(self, events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Groups events by target and calculates evidence weight."""
        clusters = {}
        for e in events:
            # Skip non-semantic events
            if e['kind'] not in ["decision", "result", "error", "config_change"]:
                continue
                
            ctx = e.get('context') or {}
            target = ctx.get('target')
            
            if not target:
                continue
                
            if target not in clusters:
                clusters[target] = {"weight": 0.0, "all_ids": [], "commits": 0, "errors": 0}
            
            clusters[target]["all_ids"].append(e['id'])
            
            # Weigh different kinds of evidence
            if e['kind'] == "decision": clusters[target]["weight"] += 1.0
            if e['kind'] == "error": clusters[target]["errors"] += 1
            if e['kind'] == "result" and ctx.get('success'): clusters[target]["weight"] += 0.5
            
        return clusters

    def run_cycle(self, after_id: Optional[int] = None, limit: int = 2000) -> Tuple[List[str], Optional[int]]:
        logger.info(f"Starting lifecycle reflection cycle [after_id={after_id}, limit={limit}]...")
        if not self.processor:
            return [], after_id
    
        result_ids = []
        max_id = after_id
        
        # Read config BEFORE entering the transaction
        arbitration_mode = self.semantic.meta.get_config("arbitration_mode", "optimal")

        with self.semantic.transaction():
            # 1. Preparation
            all_streams = self._get_all_streams()
            processed_fids = set()
            now = datetime.now()

            # 2. Evidence Aggregation
            recent_events = self.episodic.query(limit=limit, status='active', after_id=after_id, order='ASC')
            
            # Optimization: Load events into map for this batch
            all_recent_events = self.episodic.query(limit=limit + 500, status='active', after_id=after_id, order='ASC')
            event_map = {e['id']: e for e in all_recent_events}

            if recent_events:
                # CRITICAL: Always advance max_id if we have events
                max_id = max(e['id'] for e in recent_events)
                evidence_clusters = self._cluster_evidence(recent_events)
                
                if evidence_clusters:
                    logger.info(f"Reflection: Found {len(evidence_clusters)} activity clusters across targets.")
                
                # 3. Update existing streams or discover new patterns
                for target, stats in evidence_clusters.items():
                    if target in self.BLACKLISTED_TARGETS or target.lower().startswith("general"):
                        continue
                    
                    relevant_streams = [(fid, data) for fid, data in all_streams.items() if data.get('target') == target]
                    
                    if relevant_streams:
                        # Direct Update Model
                        if len(relevant_streams) == 1:
                            fid, data = relevant_streams[0]
                            self._process_stream(fid, data, stats, now, event_map=event_map, arbitration_mode=arbitration_mode, update_only=False)
                            processed_fids.add(fid)
                            result_ids.append(fid)
                        else:
                            # Handle multiple streams (Fragmentation)
                            for fid, data in relevant_streams:
                                self._process_stream(fid, data, stats, now, event_map=event_map, arbitration_mode=arbitration_mode, update_only=False)
                                processed_fids.add(fid)
                                result_ids.append(fid)
                    else:
                        if stats['weight'] >= 1.0 or stats['errors'] >= self.policy.error_threshold:
                            new_fid = self._create_pattern_stream(target, stats, now, event_map=event_map, arbitration_mode=arbitration_mode)
                            if new_fid: result_ids.append(new_fid)

            # 4. Apply Vitality Decay for unprocessed streams
            for fid, data in all_streams.items():
                if fid not in processed_fids:
                    # Logic now part of calculate_temporal_signals
                    try:
                        ctx_raw = data.get('context_json')
                        if ctx_raw:
                            ctx_dict = json.loads(ctx_raw)
                            # Ensure last_hit_at from DB overrides or merges correctly
                            ctx_dict['last_hit_at'] = data.get('last_hit_at') or ctx_dict.get('last_hit_at')
                            stream = DecisionStream(**ctx_dict)
                            updated = self.lifecycle.calculate_temporal_signals(stream, [], now)
                            if updated.vitality != stream.vitality:
                                self.processor.update_decision(fid, updated.model_dump(), commit_msg="Lifecycle: Vitality decay update.", skip_episodic=True)
                                result_ids.append(fid)
                    except Exception as e:
                        logger.error(f"Failed to process decay for {fid}: {e}")

        return result_ids, max_id

    def _process_stream(self, fid: str, data: Dict[str, Any], stats: Dict[str, Any], now: datetime, 
                        event_map: Optional[Dict[int, Any]] = None, 
                        arbitration_mode: str = "optimal",
                        update_only: bool = False):
        """Updates an existing decision stream with new evidence."""
        try:
            # Reconstruct model from stored context
            ctx_raw = data.get('context_json')
            if not ctx_raw: return
            ctx_dict = json.loads(ctx_raw)
            # Ensure last_hit_at from DB overrides or merges correctly
            ctx_dict['last_hit_at'] = data.get('last_hit_at') or ctx_dict.get('last_hit_at')
            stream = DecisionStream(**ctx_dict)
            
            # 1. Update evidence list
            if not update_only:
                new_ids = [eid for eid in stats['all_ids'] if eid not in stream.evidence_event_ids]
                if new_ids:
                    stream.evidence_event_ids.extend(new_ids)
                    if arbitration_mode != "lite":
                        stream.enrichment_status = "pending"
            
            # 2. Extract reinforcement dates
            reinforcement_dates = []
            REINFORCEMENT_KINDS = {KIND_RESULT, KIND_ERROR, "call", "task", "prompt", "intervention"}
            for eid in stats['all_ids']:
                if eid in event_map:
                    ev = event_map[eid]
                    if ev['kind'] in REINFORCEMENT_KINDS:
                        try:
                            dt = datetime.fromisoformat(ev['timestamp'])
                            reinforcement_dates.append(dt)
                        except (ValueError, TypeError): pass
            
            # 3. Update temporal signals
            stream = self.lifecycle.calculate_temporal_signals(stream, reinforcement_dates, now)
            
            # Reactivate if dormant
            if stats.get('all_ids') and stream.vitality != DecisionVitality.ACTIVE:
                stream = stream.model_copy(update={"vitality": DecisionVitality.ACTIVE})

            # 4. Phase Promotion
            old_phase = stream.phase
            stream = self.lifecycle.promote_stream(stream)
            
            # 5. Save updates
            update_data = stream.model_dump()
            self.processor.update_decision(fid, update_data, commit_msg=f"Reflection: Updated stream {fid}", skip_episodic=True)
            
        except Exception as e:
            logger.error(f"Failed to process stream {fid}: {e}")

    def _create_pattern_stream(self, target: str, stats: Dict[str, Any], now: datetime, 
                               event_map: Optional[Dict[int, Any]] = None,
                               arbitration_mode: str = "optimal") -> Optional[str]:
        """Creates a new pattern stream for a discovered target."""
        try:
            stream = DecisionStream(
                decision_id=str(uuid.uuid4()),
                target=target,
                title=f"New behavioral pattern in {target}",
                rationale=f"Observed emerging activity for {target}",
                phase=DecisionPhase.PATTERN,
                vitality=DecisionVitality.ACTIVE,
                evidence_event_ids=stats['all_ids'],
                first_seen=now,
                last_seen=now,
                frequency=0
            )
            
            # Calculate initial signals
            reinforcement_dates = []
            REINFORCEMENT_KINDS = {KIND_RESULT, KIND_ERROR, "call", "task", "prompt", "intervention"}
            for eid in stats['all_ids']:
                if eid in event_map:
                    ev = event_map[eid]
                    if ev['kind'] in REINFORCEMENT_KINDS:
                        try: reinforcement_dates.append(datetime.fromisoformat(ev['timestamp']))
                        except: pass
            
            stream = self.lifecycle.calculate_temporal_signals(stream, reinforcement_dates, now)
            
            if arbitration_mode != "lite":
                stream.enrichment_status = "pending"
                
            decision = self.processor.process_event(
                source="reflection_engine",
                kind=KIND_PROPOSAL,
                content=stream.title,
                context=stream
            )
            return decision.metadata.get("file_id")
        except Exception as e:
            logger.error(f"Failed to create pattern stream for {target}: {e}")
            return None
