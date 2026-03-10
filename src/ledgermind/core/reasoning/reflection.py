import logging
import os
import json
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from ledgermind.core.core.schemas import (
    MemoryEvent, KIND_PROPOSAL, KIND_DECISION, KIND_RESULT, KIND_ERROR, KIND_INTERVENTION,
    DecisionStream, DecisionPhase, DecisionVitality, PatternScope
)
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore
from ledgermind.core.reasoning.lifecycle import LifecycleEngine
from ledgermind.core.reasoning.trajectory import TrajectoryBuilder
from ledgermind.core.core.targets import TargetRegistry
from ledgermind.core.utils.datetime_utils import to_naive_utc

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
        
        # Initialize Trajectory Builder
        self.target_registry = TargetRegistry(storage_path=self.semantic.repo_path)
        self.trajectory_builder = TrajectoryBuilder(self.target_registry)
        
        self.BLACKLISTED_TARGETS = {"unknown", "general", "system", "knowledge_merge", "reflection_engine", "bridge"}

    def _get_all_streams(self) -> Dict[str, Dict[str, Any]]:
        """Fetch all active/draft semantic entries for cross-referencing."""
        all_metas = self.semantic.meta.list_all()
        return {m['fid']: m for m in all_metas if m.get('status') in ('active', 'draft')}

    def run_cycle(self, after_id: Optional[int] = None, limit: int = 2000) -> Tuple[List[str], Optional[int]]:
        logger.info(f"Starting lifecycle reflection cycle [after_id={after_id}, limit={limit}]...")
        if not self.processor:
            return [], after_id
    
        result_ids = []
        max_id = after_id
        
        # Read config BEFORE processing
        arbitration_mode = self.semantic.meta.get_config("arbitration_mode", "optimal")

        # NO GLOBAL TRANSACTION: Processing trajectories doesn't require a lock, 
        # and semantic.save() will handle its own granular transactions.
        
        # 1. Preparation
        all_streams = self._get_all_streams()
        now = datetime.now()

        # 2. Evidence Aggregation & Trajectory Building
        recent_events = self.episodic.query(limit=limit, status='active', after_id=after_id, order='ASC')
        
        # Optimization: Load events into map for this batch
        all_recent_events = self.episodic.query(limit=limit + 500, status='active', after_id=after_id, order='ASC')
        event_map = {e['id']: e for e in all_recent_events}

        if recent_events:
            # CRITICAL: Always advance max_id if we have events
            max_id = max(e['id'] for e in recent_events)
            
            # V5.8: Build granular chains
            chains = self.trajectory_builder.build_chains(recent_events)
            if chains:
                logger.info(f"Reflection: Analyzed {len(chains)} trajectories.")
            
            # 3. Process each chain as a potential pattern
            for chain in chains:
                target = chain.global_target
                if not target or target == "unknown" or target in self.BLACKLISTED_TARGETS:
                    continue
                
                # Calculate weight for this specific chain
                weight = 0.0
                errors = 0
                for atom in chain.atoms:
                    for e in atom.events:
                        if e.kind == "decision": weight += 1.0
                        if e.kind == "error": errors += 1
                        if e.kind == "result" and isinstance(e.context, dict) and e.context.get('success'): 
                            weight += 0.5
                        if e.kind == "call": weight += 0.1
                
                # V6.5: Strict atomicity - always create a new proposal for a significant trajectory
                if weight >= 0.5 or errors >= self.policy.error_threshold:
                    stats = {
                        "weight": weight,
                        "errors": errors,
                        "all_ids": chain.all_event_ids
                    }
                    new_fid = self._create_pattern_stream(target, stats, now, 
                                                          event_map=event_map, 
                                                          arbitration_mode=arbitration_mode,
                                                          keywords=getattr(chain, 'keywords', []))
                    if new_fid: result_ids.append(new_fid)

        # 4. Apply Vitality Decay for existing streams
        for fid, data in all_streams.items():
            try:
                ctx_raw = data.get('context_json')
                if ctx_raw:
                    ctx_dict = json.loads(ctx_raw)
                    # Ensure last_hit_at from DB overrides or merges correctly
                    ctx_dict['last_hit_at'] = data.get('last_hit_at') or ctx_dict.get('last_hit_at')
                    stream = DecisionStream(**ctx_dict)
                    updated = self.lifecycle.calculate_temporal_signals(stream, [], now)
                    
                    # V5.0: Update dynamic risk/utility metrics
                    updated.estimated_utility = self.lifecycle.estimate_utility(updated)
                    updated.estimated_removal_cost = self.lifecycle.estimate_removal_cost(updated)
                    
                    if updated.vitality != stream.vitality or updated.estimated_utility != stream.estimated_utility:
                        self.processor.update_decision(fid, updated.model_dump(mode='json'), commit_msg="Lifecycle: Metrics and vitality update.", skip_episodic=True)
                        result_ids.append(fid)
            except Exception as e:
                logger.error(f"Failed to process decay for {fid}: {e}")

        return result_ids, max_id

    def _create_pattern_stream(self, target: str, stats: Dict[str, Any], now: datetime, 
                               event_map: Optional[Dict[int, Any]] = None,
                               arbitration_mode: str = "optimal",
                               keywords: List[str] = None) -> Optional[str]:
        """Creates a new pattern stream for a discovered target."""
        try:
            # V6.0: Calculate actual time range from evidence events
            event_times = []
            for eid in stats['all_ids']:
                if event_map and eid in event_map:
                    try:
                        # Use to_naive_utc for consistent comparison
                        ts = to_naive_utc(event_map[eid]['timestamp'])
                        if ts: event_times.append(ts)
                    except: pass
            
            # Normalize 'now' as well
            now_normalized = to_naive_utc(now)
            first_seen = min(event_times) if event_times else now_normalized
            last_seen = max(event_times) if event_times else now_normalized

            stream = DecisionStream(
                decision_id=str(uuid.uuid4()),
                target=target,
                title=f"Hypothesis for {target}",
                rationale=f"Observed emerging activity for {target}",
                phase=DecisionPhase.PATTERN,
                vitality=DecisionVitality.ACTIVE,
                evidence_event_ids=stats['all_ids'],
                first_seen=first_seen,
                last_seen=last_seen,
                frequency=0,
                keywords=keywords or [],
                strengths=[],
                objections=[],
                consequences=[],
                procedural=None
            )
            
            # Calculate initial signals
            reinforcement_dates = []
            REINFORCEMENT_KINDS = {KIND_RESULT, KIND_ERROR, "call", "task", "prompt", "intervention"}
            for eid in stats['all_ids']:
                if eid in event_map:
                    ev = event_map[eid]
                    if ev['kind'] in REINFORCEMENT_KINDS:
                        try:
                            dt = datetime.fromisoformat(ev['timestamp'].replace('Z', '+00:00'))
                            reinforcement_dates.append(dt)
                        except (ValueError, TypeError): pass
            
            stream = self.lifecycle.calculate_temporal_signals(stream, reinforcement_dates, now)
            
            if arbitration_mode != "lite":
                stream.enrichment_status = "pending"
            
            # Persist via process_event (V5.0 standard)
            # This call will automatically acquire the necessary locks and savepoints
            decision = self.processor.process_event(
                source="reflection_engine",
                kind=KIND_PROPOSAL,
                content=stream.title,
                context=stream,
                timestamp=now
            )
            
            # Extract file_id from decision metadata
            fid = decision.metadata.get("file_id")
            return fid
            
        except Exception as e:
            logger.error(f"Failed to create pattern stream for {target}: {e}")
            return None
