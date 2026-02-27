
import logging
import os
import json
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from ledgermind.core.core.schemas import (
    MemoryEvent, KIND_PROPOSAL, KIND_DECISION, KIND_RESULT, KIND_ERROR,
    DecisionStream, DecisionPhase, DecisionVitality, PatternScope
)
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore
from ledgermind.core.reasoning.distillation import DistillationEngine
from ledgermind.core.reasoning.lifecycle import LifecycleEngine

logger = logging.getLogger(__name__)

class ReflectionPolicy:
    def __init__(self, 
                 error_threshold: int = 1,
                 success_threshold: int = 2,
                 min_confidence: float = 0.3,
                 observation_window_hours: int = 168,
                 decay_rate: float = 0.05,
                 ready_threshold: float = 0.6,
                 auto_accept_threshold: float = 0.9,
                 distillation_window_size: int = 5):
        self.error_threshold = error_threshold
        self.success_threshold = success_threshold
        self.min_confidence = min_confidence
        self.observation_window = timedelta(hours=observation_window_hours)
        self.decay_rate = decay_rate
        self.ready_threshold = ready_threshold
        self.auto_accept_threshold = auto_accept_threshold
        self.distillation_window_size = distillation_window_size

class ReflectionEngine:
    """
    Reflection Engine v5.0: Behavior Observer and Lifecycle Manager.
    """
    BLACKLISTED_TARGETS = {"general", "general_development", "general_task", "unknown", "none", "null"}

    def __init__(self, episodic_store: EpisodicStore, semantic_store: SemanticStore, 
                 policy: Optional[ReflectionPolicy] = None,
                 processor: Any = None):
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.policy = policy or ReflectionPolicy()
        self.processor = processor
        self.lifecycle = LifecycleEngine(observation_window_days=self.policy.observation_window.total_seconds()/86400.0)
        if not self.processor:
            logger.warning("ReflectionEngine initialized without a high-level processor.")

    def run_cycle(self, after_id: Optional[int] = None) -> Tuple[List[str], Optional[int]]:
        logger.info(f"Starting lifecycle reflection cycle [after_id={after_id}]...")
        if not self.processor:
            return [], after_id

        result_ids = []
        max_id = after_id
        

        with self.semantic.transaction():
            # 0. Distillation (Procedural Patterns)
            distiller = DistillationEngine(self.episodic, window_size=self.policy.distillation_window_size)
            procedural_proposals = distiller.distill_trajectories(after_id=after_id)
            
            for prop in procedural_proposals:
                if prop.target in self.BLACKLISTED_TARGETS or prop.target.lower().startswith("general"):
                    continue

                decision = self.processor.process_event(
                    source="reflection_engine",
                    kind=KIND_PROPOSAL,
                    content=prop.title,
                    context=prop
                )
                if decision.should_persist:
                    result_ids.append(decision.metadata.get("file_id"))

            # 1. Evidence Aggregation
            recent_events = self.episodic.query(limit=1000, status='active', after_id=after_id, order='ASC')
            if not recent_events:
                return result_ids, max_id
                
            max_id = max(e['id'] for e in recent_events)
            evidence_clusters = self._cluster_evidence(recent_events)
            
            # Optimization: Load all active events once to avoid N+1 queries in _process_stream
            all_recent_events = self.episodic.query(limit=2000, status='active', order='ASC')
            event_map = {e['id']: e for e in all_recent_events}

            all_streams = self._get_all_streams()
            processed_fids = set()
            now = datetime.now()
            
            # 2. Update existing streams or discover new patterns
            for target, stats in evidence_clusters.items():
                if target in self.BLACKLISTED_TARGETS or target.lower().startswith("general"):
                    continue
                
                relevant_streams = [(fid, data) for fid, data in all_streams.items() if data['context'].get('target') == target]
                
                if relevant_streams:
                    for fid, data in relevant_streams:
                        self._process_stream(fid, data, stats, now, event_map=event_map)
                        processed_fids.add(fid)
                        result_ids.append(fid)
                else:
                    # New pattern
                    if stats['commits'] >= 1 or stats['successes'] >= 1 or stats['errors'] >= 1:
                        new_fid = self._create_pattern_stream(target, stats, now)
                        if new_fid: result_ids.append(new_fid)

            # 3. Apply Vitality Decay for unprocessed streams
            for fid, data in all_streams.items():
                if fid not in processed_fids:
                    stream = DecisionStream(**data['context'])
                    stream = self.lifecycle.update_vitality(stream, now)
                    self.processor.update_decision(fid, stream.model_dump(), commit_msg="Lifecycle: Vitality decay update.")
                
        return result_ids, max_id

    def _process_stream(self, fid: str, data: Dict[str, Any], stats: Dict[str, Any], now: datetime, event_map: Optional[Dict[int, Any]] = None):
        stream = DecisionStream(**data['context'])
        
        # Collect timestamps
        if event_map is None:
            events = self.episodic.query(limit=1000, status='active', order='ASC')
            event_map = {e['id']: e for e in events}
        
        reinforcement_dates = []
        all_evidence = set(stream.evidence_event_ids + stats['all_ids'])
        stream.evidence_event_ids = list(all_evidence)
        
        for eid in stream.evidence_event_ids:
            if eid in event_map:
                try:
                    dt = datetime.fromisoformat(event_map[eid]['timestamp'])
                    reinforcement_dates.append(dt)
                except:
                    pass
        
        if not reinforcement_dates:
            reinforcement_dates = [now]
            
        stream = self.lifecycle.calculate_temporal_signals(stream, reinforcement_dates, now)
        stream = self.lifecycle.update_vitality(stream, now)
        stream = self.lifecycle.promote_stream(stream)
        
        self.processor.update_decision(fid, stream.model_dump(), commit_msg=f"Lifecycle: Promoted/Updated stream to {stream.phase.value}")

    def _create_pattern_stream(self, target: str, stats: Dict[str, Any], now: datetime) -> str:
        stream = DecisionStream(
            decision_id=str(uuid.uuid4()),
            target=target,
            title=f"Behavioral pattern in {target}",
            rationale=f"Observed emerging activity for {target}",
            phase=DecisionPhase.PATTERN,
            vitality=DecisionVitality.ACTIVE,
            evidence_event_ids=stats['all_ids'],
            first_seen=now,
            last_seen=now,
            frequency=len(stats['all_ids'])
        )
        
        # Calculate initial temporal signals
        stream = self.lifecycle.calculate_temporal_signals(stream, [now], now)
        stream = self.lifecycle.promote_stream(stream)
        
        decision = self.processor.process_event(source="reflection_engine", kind=KIND_PROPOSAL, content=stream.title, context=stream)
        return decision.metadata.get("file_id") if decision.should_persist else ""

    def _cluster_evidence(self, events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        clusters = {}
        last_valid_target = None
        for ev in events:
            if ev.get('source') == 'reflection_engine': continue
            ctx = ev.get('context', {})
            target = ctx.get('target')
            
            if ev['kind'] == 'commit_change' and (not target or target in self.BLACKLISTED_TARGETS or len(target) < 3):
                import re
                msg = ev.get('content', '')
                match = re.search(r'\(([^)]+)\):', msg)
                target = match.group(1) if match else target or "general_development"

            # Inheritance: only for results that don't have their own target
            if not target and ev['kind'] == KIND_RESULT:
                target = last_valid_target

            target = target or "general"
            
            # Update last valid target if this one is good, otherwise RESET it if it's a new prompt/decision
            if target not in self.BLACKLISTED_TARGETS and target.lower() != "general" and len(target) >= 3:
                last_valid_target = target
            elif ev['kind'] in ('prompt', 'decision', 'task'):
                last_valid_target = None
                
            if target in self.BLACKLISTED_TARGETS or target.lower().startswith("general") or len(target) < 3:
                continue
            
            if target not in clusters:
                clusters[target] = {'errors': 0.0, 'successes': 0.0, 'commits': 0, 'all_ids': [], 'last_seen': ev['timestamp']}
            
            clusters[target]['all_ids'].append(ev['id'])
            
            if ev['kind'] == KIND_ERROR: clusters[target]['errors'] += 1.0
            elif ev['kind'] == KIND_RESULT:
                score = ctx.get('success', 0.5)
                if score is True: score = 1.0
                elif score is False: score = 0.0
                clusters[target]['successes'] += float(score)
                clusters[target]['errors'] += (1.0 - float(score))
            elif ev['kind'] == 'commit_change': clusters[target]['commits'] += 1
            
            try: clusters[target]['last_seen'] = max(clusters[target]['last_seen'], ev['timestamp'])
            except: pass
        return clusters

    def _get_all_streams(self) -> Dict[str, Dict[str, Any]]:
        streams = {}
        # Fetch proposals, decisions and interventions which might be encoded as streams
        metas = self.semantic.meta.list_all()
        # Filter by kind and validate structure (Issue #7)
        for m in metas:
            if m.get('kind') not in (KIND_PROPOSAL, KIND_DECISION, KIND_INTERVENTION):
                continue
                
            fid = m['fid']
            try:
                ctx = json.loads(m.get('context_json', '{}'))
                # Robust check: must have either phase or decision_id
                if "phase" in ctx or "decision_id" in ctx:
                    # Validate via Pydantic to ensure it's a valid stream
                    try:
                        DecisionStream(**ctx)
                        streams[fid] = {
                            'kind': m.get('kind'),
                            'content': m.get('content'),
                            'timestamp': m.get('timestamp'),
                            'context': ctx
                        }
                    except Exception:
                        # Fallback for old records: if it has decision_id but fails validation, 
                        # it might be a pre-v2.9 stream. We'll include it for the migrator.
                        if "decision_id" in ctx:
                             streams[fid] = {
                                'kind': m.get('kind'),
                                'content': m.get('content'),
                                'timestamp': m.get('timestamp'),
                                'context': ctx
                            }
            except Exception: continue
        return streams
