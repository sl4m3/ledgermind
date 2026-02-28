
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
    BLACKLISTED_TARGETS = {
        "general", "general_development", "general_task", "unknown", "none", "null",
        "reflection_engine"
    }

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
        
        # Read config BEFORE entering the transaction to prevent implicit DDL commits in SQLite
        arbitration_mode = self.semantic.meta.get_config("arbitration_mode", "lite")

        with self.semantic.transaction():
            # 0. Distillation (Procedural Patterns)
            distiller = DistillationEngine(self.episodic, window_size=self.policy.distillation_window_size)
            procedural_proposals = distiller.distill_trajectories(after_id=after_id)

            # Group procedural proposals by target for linking
            target_to_procedural = {}

            for prop in procedural_proposals:
                if prop.target in self.BLACKLISTED_TARGETS or prop.target.lower().startswith("general"):
                    continue

                if arbitration_mode != "lite":
                    # Mark for asynchronous enrichment
                    prop.enrichment_status = "pending"

                
                if prop.target not in target_to_procedural:
                    target_to_procedural[prop.target] = []
                target_to_procedural[prop.target].append(prop)

                decision = self.processor.process_event(
                    source="reflection_engine",
                    kind=KIND_PROPOSAL,
                    content=prop.title,
                    context=prop
                )
                if decision.should_persist:
                    fid = decision.metadata.get("file_id")
                    result_ids.append(fid)
                    # Add fid to our mapping for linking
                    prop.keywords.append(f"fid:{fid}") # Hack to pass fid back or we could use a better way

            # 1. Evidence Aggregation
            recent_events = self.episodic.query(limit=2000, status='active', after_id=after_id, order='ASC')
            
            # Optimization: Load all active events once to avoid N+1 queries in _process_stream
            all_recent_events = self.episodic.query(limit=3000, status='active', order='ASC')
            event_map = {e['id']: e for e in all_recent_events}

            all_streams = self._get_all_streams()
            processed_fids = set()
            now = datetime.now()

            if recent_events:
                max_id = max(e['id'] for e in recent_events)
                evidence_clusters = self._cluster_evidence(recent_events)
                
                # 2. Update existing streams or discover new patterns
                for target, stats in evidence_clusters.items():
                    if target in self.BLACKLISTED_TARGETS or target.lower().startswith("general"):
                        continue
                    
                    relevant_streams = [(fid, data) for fid, data in all_streams.items() if data['context'].get('target') == target]
                    procedural_list = target_to_procedural.get(target, [])
                    
                    if relevant_streams:
                        for fid, data in relevant_streams:
                            self._process_stream(fid, data, stats, now, event_map=event_map, procedural_links=procedural_list)
                            processed_fids.add(fid)
                            result_ids.append(fid)
                    else:
                        # New pattern based on accumulated session weight
                        if stats['weight'] >= 1.0 or stats['commits'] >= 1:
                            new_fid = self._create_pattern_stream(target, stats, now, event_map=event_map, procedural_links=procedural_list)
                            if new_fid: result_ids.append(new_fid)

            # 3. Apply Vitality Decay for unprocessed streams (always run this)
            for fid, data in all_streams.items():
                if fid not in processed_fids:
                    stream = DecisionStream(**data['context'])
                    old_vit = stream.vitality
                    stream = self.lifecycle.update_vitality(stream, now)
                    
                    days = (now - stream.last_seen).total_seconds() / 86400.0
                    logger.debug(f"Decay check for {fid} ({stream.target}): last_seen={stream.last_seen}, days={days:.2f}, vit={old_vit}->{stream.vitality}")

                    # Only update if vitality or confidence actually changed to avoid churn
                    if stream.vitality != old_vit or abs(stream.confidence - data['context'].get('confidence', 0)) > 0.01:
                        logger.info(f"Applying vitality decay to {fid}: {old_vit} -> {stream.vitality} (days={days:.2f})")
                        self.processor.update_decision(fid, stream.model_dump(), commit_msg="Lifecycle: Vitality decay update.")
                        result_ids.append(fid)

            # 4. Log Reflection Summary if any changes were made
            if result_ids:
                summary_event = MemoryEvent(
                    source="reflection_engine",
                    kind="reflection_summary",
                    content=f"Reflection cycle completed. Distilled or updated {len(set(result_ids))} knowledge records.",
                    context={"updated_fids": list(set(result_ids))}
                )
                self.episodic.append(summary_event)
                
        return result_ids, max_id

    def _process_stream(self, fid: str, data: Dict[str, Any], stats: Dict[str, Any], now: datetime, 
                        event_map: Optional[Dict[int, Any]] = None, 
                        procedural_links: Optional[List[ProposalContent]] = None):
        stream = DecisionStream(**data['context'])
        
        # Collect timestamps
        if event_map is None:
            events = self.episodic.query(limit=1000, status='active', order='ASC')
            event_map = {e['id']: e for e in events}
        
        reinforcement_dates = []
        all_evidence = set(stream.evidence_event_ids + stats['all_ids'])
        stream.evidence_event_ids = list(all_evidence)
        
        # Link procedural instructions if provided
        if procedural_links:
            for prop in procedural_links:
                if prop.procedural and prop.confidence >= 0.7:
                    # Attach the most confident procedural content directly to the stream
                    if not stream.procedural or prop.confidence > stream.confidence:
                        stream.procedural = prop.procedural
                    
                    # Also keep track of dedicated procedural IDs
                    for kw in prop.keywords:
                        if kw.startswith("fid:"):
                            proc_fid = kw.split(":", 1)[1]
                            if proc_fid not in stream.procedural_ids:
                                stream.procedural_ids.append(proc_fid)
        
        # Define kinds that constitute a real 'use' or 'reinforcement' of knowledge (PR #30)
        REINFORCEMENT_KINDS = {KIND_RESULT, KIND_ERROR, "call", "task", "prompt", "intervention"}

        for eid in stream.evidence_event_ids:
            if eid in event_map:
                ev = event_map[eid]
                if ev['kind'] in REINFORCEMENT_KINDS:
                    try:
                        dt = datetime.fromisoformat(ev['timestamp'])
                        reinforcement_dates.append(dt)
                    except:
                        pass
        
        if not reinforcement_dates:
            reinforcement_dates = [now]
            
        stream = self.lifecycle.calculate_temporal_signals(stream, reinforcement_dates, now)
        
        # Issue #14: Reactivate dormant stream if new events arrived in this cluster
        if stats.get('all_ids'):
            if stream.vitality == DecisionVitality.DORMANT:
                logger.info(f"Reactivating dormant stream: {stream.target}")
                stream.vitality = DecisionVitality.ACTIVE
                
        stream = self.lifecycle.update_vitality(stream, now)
        stream = self.lifecycle.promote_stream(stream)
        
        # Normative upgrade: Proposal -> Decision based on balanced model (PR #45)
        current_kind = data.get('kind', KIND_PROPOSAL)
        new_kind = current_kind
        
        if current_kind == KIND_PROPOSAL:
            new_kind = self.lifecycle.evaluate_normative_authority(stream)
            if new_kind == KIND_DECISION:
                logger.info(f"Normative Upgrade: {stream.target} is now a DECISION.")
        
        # Merge kind into update data
        update_data = stream.model_dump()
        update_data['kind'] = new_kind

        self.processor.update_decision(fid, update_data, commit_msg=f"Lifecycle: Promoted/Updated stream to {stream.phase.value} ({new_kind})")

    def _create_pattern_stream(self, target: str, stats: Dict[str, Any], now: datetime, 
                               event_map: Optional[Dict[int, Any]] = None,
                               procedural_links: Optional[List[ProposalContent]] = None) -> str:
        # Read config to check if enrichment is enabled
        arbitration_mode = self.semantic.meta.get_config("arbitration_mode", "lite")

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

        if arbitration_mode != "lite":
            stream.enrichment_status = "pending"

        # Link procedural instructions if provided
        if procedural_links:
            for prop in procedural_links:
                if prop.procedural and prop.confidence >= 0.7:
                    if not stream.procedural or prop.confidence > stream.confidence:
                        stream.procedural = prop.procedural
                    
                    for kw in prop.keywords:
                        if kw.startswith("fid:"):
                            proc_fid = kw.split(":", 1)[1]
                            if proc_fid not in stream.procedural_ids:
                                stream.procedural_ids.append(proc_fid)
        
        reinforcement_dates = []
        if event_map:
            REINFORCEMENT_KINDS = {KIND_RESULT, KIND_ERROR, "call", "task", "prompt", "intervention"}
            for eid in stats['all_ids']:
                if eid in event_map:
                    ev = event_map[eid]
                    if ev['kind'] in REINFORCEMENT_KINDS:
                        try:
                            dt = datetime.fromisoformat(ev['timestamp'])
                            reinforcement_dates.append(dt)
                        except:
                            pass
                            
        if not reinforcement_dates:
            reinforcement_dates = [now]
        
        # Calculate initial temporal signals
        stream = self.lifecycle.calculate_temporal_signals(stream, reinforcement_dates, now)
        stream = self.lifecycle.promote_stream(stream)
        
        decision = self.processor.process_event(source="reflection_engine", kind=KIND_PROPOSAL, content=stream.title, context=stream)
        return decision.metadata.get("file_id") if decision.should_persist else ""

    def _cluster_evidence(self, events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        clusters = {}
        last_valid_target = None
        
        # Meta-events that should never trigger learning or be used as evidence
        META_KINDS = {KIND_PROPOSAL, "context_snapshot", "context_injection"}
        
        # Russian success indicators
        RU_SUCCESS_KEYWORDS = {"успешно", "прошли", "исправлено", "завершено", "ок", "выполнено", "готово", "работает", "прошел", "починил", "успех"}

        for ev in events:
            # 1. Anti-Self-Reflection: Skip events from engine or meta-events
            if ev.get('source') == 'reflection_engine': continue
            if ev.get('kind') in META_KINDS: continue
            
            ctx = ev.get('context', {})
            target = ctx.get('target')
            content = ev.get('content', '').lower()
            
            if ev['kind'] == 'commit_change' and (not target or target in self.BLACKLISTED_TARGETS or len(target) < 3):
                import re
                # 1. Try conventional commit pattern: feat(core): ...
                match = re.search(r'\(([^)]+)\):', content)
                if match:
                    target = match.group(1)
                else:
                    # 2. Try to infer target from changed files
                    changed_files = ctx.get('changed_files', [])
                    if changed_files:
                        # Find most common top-level directory/module
                        paths = [f.split('/')[0] for f in changed_files if '/' in f]
                        if not paths: # Files in root
                            paths = [f.split('.')[0] for f in changed_files]
                        
                        if paths:
                            from collections import Counter
                            target = Counter(paths).most_common(1)[0][0]

            # Inheritance: results and calls inherit target from previous context (PR #42)
            if not target and ev['kind'] in (KIND_RESULT, "call", "task", "commit_change"):
                target = last_valid_target

            target = target or "general"
            
            # Update last valid target if this one is good
            if target not in self.BLACKLISTED_TARGETS and target.lower() != "general" and len(target) >= 3:
                last_valid_target = target
            elif ev['kind'] in ('prompt', 'decision'):
                # Issue Fix: Don't reset to None immediately. 
                # Only reset if the prompt explicitly has a different target or after a period of time
                if target and target not in self.BLACKLISTED_TARGETS and target != "general":
                    last_valid_target = target
                # If we really want to reset, we should do it based on session gap, not just every prompt
                
            if target in self.BLACKLISTED_TARGETS or target.lower().startswith("general") or len(target) < 3:
                continue
            
            if target not in clusters:
                clusters[target] = {'errors': 0.0, 'successes': 0.0, 'commits': 0, 'all_ids': [], 'last_seen': ev['timestamp'], 'weight': 0.0}
            
            clusters[target]['all_ids'].append(ev['id'])
            
            # kind-based weighting
            if ev['kind'] == KIND_ERROR: 
                clusters[target]['errors'] += 1.0
                clusters[target]['weight'] += 0.5
            elif ev['kind'] == KIND_RESULT:
                score = ctx.get('success', 0.5)
                # Localization support: check for Russian success words
                is_ru_success = any(word in content for word in RU_SUCCESS_KEYWORDS)
                
                if score is True or is_ru_success: score = 1.0
                elif score is False: score = 0.0
                
                clusters[target]['successes'] += float(score)
                clusters[target]['errors'] += (1.0 - float(score))
                clusters[target]['weight'] += 1.0 if score > 0.7 else 0.2
            elif ev['kind'] == 'commit_change': 
                clusters[target]['commits'] += 1
                clusters[target]['weight'] += 2.0
            elif ev['kind'] in ('call', 'task'):
                clusters[target]['weight'] += 0.3
            elif ev['kind'] == 'prompt':
                clusters[target]['weight'] += 0.2
            
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
                    # Inject latest metrics from database into context
                    ctx['hit_count'] = m.get('hit_count', 0)
                    ctx['confidence'] = m.get('confidence', ctx.get('confidence', 1.0))
                    ctx['phase'] = m.get('phase', ctx.get('phase', 'pattern'))
                    ctx['vitality'] = m.get('vitality', ctx.get('vitality', 'active'))
                    # Synchronize last_seen with database timestamp for accurate decay (PR #28)
                    if m.get('timestamp'):
                        ctx['last_seen'] = m.get('timestamp')

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
