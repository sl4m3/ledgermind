import logging
import os
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from ledgermind.core.core.schemas import (
    MemoryEvent, KIND_PROPOSAL, ProposalContent, ProposalStatus, 
    KIND_RESULT, KIND_ERROR
)
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore
from ledgermind.core.reasoning.distillation import DistillationEngine

logger = logging.getLogger(__name__)

class ReflectionPolicy:
    def __init__(self, 
                 error_threshold: int = 1,
                 success_threshold: int = 2,
                 min_confidence: float = 0.3,
                 observation_window_hours: int = 1,
                 decay_rate: float = 0.05,
                 ready_threshold: float = 0.6,
                 auto_accept_threshold: float = 0.9):
        self.error_threshold = error_threshold
        self.success_threshold = success_threshold
        self.min_confidence = min_confidence
        self.observation_window = timedelta(hours=observation_window_hours)
        self.decay_rate = decay_rate
        self.ready_threshold = ready_threshold
        self.auto_accept_threshold = auto_accept_threshold

class ReflectionEngine:
    """
    Reflection Engine v4.3: Incremental Proactive Knowledge Discovery.
    """
    BLACKLISTED_TARGETS = {"general", "general_development", "general_task", "unknown", "none", "null"}

    def __init__(self, episodic_store: EpisodicStore, semantic_store: SemanticStore, 
                 policy: Optional[ReflectionPolicy] = None,
                 processor: Any = None):
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.policy = policy or ReflectionPolicy()
        self.processor = processor
        if not self.processor:
            logger.warning("ReflectionEngine initialized without a high-level processor.")

    def run_cycle(self, after_id: Optional[int] = None) -> Tuple[List[str], Optional[int]]:
        """
        Runs an incremental reflection cycle.
        Returns (list of created/updated proposal IDs, last processed event ID).
        """
        logger.info(f"Starting incremental reflection cycle [after_id={after_id}]...")
        if not self.processor:
            logger.error("ReflectionEngine cannot run: No processor available.")
            return [], after_id

        result_ids = []
        max_id = after_id
        
        with self.semantic.transaction():
            # 0. Distillation (Procedural Patterns)
            distiller = DistillationEngine(self.episodic)
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

            # 1. Evidence Aggregation (Forward from after_id)
            recent_events = self.episodic.query(limit=1000, status='active', after_id=after_id, order='ASC')
            if not recent_events:
                return result_ids, max_id
                
            max_id = max(e['id'] for e in recent_events)
            evidence_clusters = self._cluster_evidence(recent_events)
            
            all_drafts = self._get_all_draft_proposals()
            active_decisions = self._get_active_decision_targets()
            processed_fids = set()
            
            # 2. Update existing hypotheses or discover new ones
            for target, stats in evidence_clusters.items():
                if target in self.BLACKLISTED_TARGETS or target.lower().startswith("general"):
                    continue
                
                relevant_proposals = self._find_proposals_by_target(all_drafts, target)
                
                for fid, data in relevant_proposals:
                    self._evaluate_hypothesis(fid, data, stats)
                    processed_fids.add(fid)
                    result_ids.append(fid)
                
                # 3. Knowledge Discovery
                if stats['errors'] >= self.policy.error_threshold:
                    if not any(p[1]['context'].get('confidence', 0.0) > 0.6 for p in relevant_proposals):
                        new_fids = self._generate_competing_hypotheses(target, stats)
                        result_ids.extend(new_fids)
                
                elif stats['successes'] >= self.policy.success_threshold and target not in active_decisions:
                    if not relevant_proposals:
                        new_fid = self._generate_success_proposal(target, stats)
                        if new_fid: result_ids.append(new_fid)

                elif stats['commits'] >= 2 and target not in active_decisions:
                    if not relevant_proposals:
                        new_fid = self._generate_evolution_proposal(target, stats)
                        if new_fid: result_ids.append(new_fid)

            # 4. Decay and Automatic Readiness
            now = datetime.now()
            for fid, data in all_drafts.items():
                if fid not in processed_fids:
                    # Apply decay only if time passed (heuristic: check timestamp of draft)
                    self._apply_decay(fid, data)
                
                # Check for Automatic Readiness & Acceptance
                self._check_proposal_lifecycle(fid, data, now)
                
        return result_ids, max_id

    def _check_proposal_lifecycle(self, fid: str, data: Dict[str, Any], now: datetime):
        ctx = data['context']
        if not ctx.get('ready_for_review'):
            try:
                first_seen = datetime.fromisoformat(ctx['first_observed_at'])
                if (now - first_seen) >= self.policy.observation_window:
                    if ctx.get('confidence', 0.0) >= self.policy.ready_threshold:
                        logger.info(f"Reflection: Proposal {fid} is now ready for review.")
                        self.processor.update_decision(fid, {"ready_for_review": True}, 
                                                    commit_msg="Reflection: Automatic readiness update.")
            except (ValueError, KeyError, TypeError): pass

        meta = self.semantic.meta.get_by_fid(fid)
        if meta:
            curr_ctx = json.loads(meta.get('context_json', '{}'))
            if (curr_ctx.get('ready_for_review') and 
                curr_ctx.get('confidence', 0.0) >= self.policy.auto_accept_threshold and
                not curr_ctx.get('objections')):
                
                logger.info(f"Reflection: Auto-Accepting proposal {fid}")
                try:
                    if hasattr(self.processor, 'accept_proposal'):
                        self.processor.accept_proposal(fid)
                except Exception as e:
                    logger.error(f"Auto-acceptance failed: {e}")

    def _get_active_decision_targets(self) -> set:
        return self.semantic.meta.list_active_targets()

    def _generate_success_proposal(self, target: str, stats: Dict[str, Any]) -> str:
        # 2.9: Try to distill procedural steps for this success
        distiller = DistillationEngine(self.episodic)
        # Mocking events for distiller to extract steps
        recent_events = self.episodic.query(limit=100, after_id=min(stats['all_ids'])-1 if stats['all_ids'] else 0, order='ASC')
        target_events = [e for e in recent_events if e['id'] in stats['all_ids']]
        
        procedural = None
        if target_events:
            temp_prop = distiller._create_procedural_proposal(target_events[:-1], target_events[-1])
            procedural = temp_prop.procedural

        h = ProposalContent(
            title=f"Best Practice for {target}",
            target=target,
            rationale=f"Observed {stats['successes']} successful operations. This pattern should be formalized.",
            confidence=0.6,
            strengths=["Based on verified positive outcomes", "Codifies successful workflow"],
            evidence_event_ids=stats['all_ids'],
            procedural=procedural, # Добавляем дистиллированные шаги
            first_observed_at=datetime.now()
        )
        if self.processor:
             decision = self.processor.process_event(source="reflection_engine", kind=KIND_PROPOSAL, content=h.title, context=h)
             return decision.metadata.get("file_id") if decision.should_persist else ""
        return ""

    def _generate_evolution_proposal(self, target: str, stats: Dict[str, Any]) -> str:
        messages = []
        for e in stats['commit_events']:
            msg = e.get('context', {}).get('full_message', '')
            if not msg:
                msg = e.get('content', '')
            if msg:
                messages.append(msg.split('\n')[0])
        
        summary = "; ".join(messages[:3])

        # Try to distill steps from commits
        distiller = DistillationEngine(self.episodic)
        procedural = None
        if stats['commit_events']:
             temp_prop = distiller._create_procedural_proposal(stats['commit_events'], stats['commit_events'][-1])
             procedural = temp_prop.procedural
        
        h = ProposalContent(
            title=f"Evolving Pattern in {target}",
            target=target,
            rationale=f"Active development detected ({stats['commits']} commits). Recent changes: {summary}.",
            confidence=0.5,
            strengths=["Reflects actual code changes", "Keeps memory in sync with codebase"],
            evidence_event_ids=stats['all_ids'],
            procedural=procedural, # Добавляем шаги (в данном случае - коммиты)
            first_observed_at=datetime.now()
        )
        if self.processor:
             decision = self.processor.process_event(source="reflection_engine", kind=KIND_PROPOSAL, content=h.title, context=h)
             return decision.metadata.get("file_id") if decision.should_persist else ""
        return ""

    def _cluster_evidence(self, events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        clusters = {}
        last_valid_target = None
        for ev in events:
            ctx = ev.get('context', {})
            target = ctx.get('target')
            
            if ev['kind'] == 'commit_change' and (not target or target in self.BLACKLISTED_TARGETS or len(target) < 3):
                msg = ev.get('content', '')
                import re
                match = re.search(r'\(([^)]+)\):', msg)
                target = match.group(1) if match else target or "general_development"

            # Inheritance: if target is missing and it's a prompt/result/decision, use last seen target
            if not target and ev['kind'] in ('prompt', 'result', 'decision'):
                target = last_valid_target

            target = target or "general"
            
            # Update last valid target if this one is good
            if target not in self.BLACKLISTED_TARGETS and target.lower() != "general" and len(target) >= 3:
                last_valid_target = target
            
            # Strict validation for target length (Pydantic requires >= 3)
            if target in self.BLACKLISTED_TARGETS or target.lower().startswith("general") or len(target) < 3:
                continue
            
            if target not in clusters:
                clusters[target] = {
                    'errors': 0.0, 'successes': 0.0, 'commits': 0,
                    'error_events': [], 'success_events': [], 'commit_events': [],
                    'all_ids': [],
                    'last_seen': ev['timestamp']
                }
            
            # Record every event ID matching this target
            clusters[target]['all_ids'].append(ev['id'])
            
            if ev['kind'] == KIND_ERROR:
                clusters[target]['errors'] += 1.0
                clusters[target]['error_events'].append(ev)
            elif ev['kind'] == KIND_RESULT:
                # Use float success score [0, 1]
                score = ctx.get('success')
                # Handle legacy boolean or missing values
                if score is True: score = 1.0
                elif score is False: score = 0.0
                elif score is None: score = 0.5 # Neutral
                
                clusters[target]['successes'] += float(score)
                clusters[target]['errors'] += (1.0 - float(score))
                
                if score >= 0.5:
                    clusters[target]['success_events'].append(ev)
                else:
                    clusters[target]['error_events'].append(ev)
            elif ev['kind'] == 'commit_change':
                clusters[target]['commits'] += 1
                clusters[target]['commit_events'].append(ev)
                
            try:
                clusters[target]['last_seen'] = max(clusters[target]['last_seen'], ev['timestamp'])
            except (KeyError, TypeError): pass
        return clusters

    def _evaluate_hypothesis(self, fid: str, data: Dict[str, Any], stats: Dict[str, Any]):
        ctx = data['context']
        new_errors = ctx.get('hit_count', 0) + stats['errors']
        new_successes = ctx.get('miss_count', 0) + stats['successes']
        
        objections = list(set(ctx.get('objections', [])))
        if stats['successes'] > 0:
            objections.append(f"Falsification Signal: {stats['successes']} successes observed in target area.")
        
        total_observations = new_errors + new_successes
        if total_observations == 0: return
        
        base_rate = new_errors / total_observations
        epistemic_penalty = (new_successes * 2) / (new_errors + 1)
        confidence = max(0.0, base_rate - epistemic_penalty)
        
        if confidence <= 0.05 and new_successes > new_errors:
            self.processor.update_decision(fid, {
                "status": ProposalStatus.FALSIFIED,
                "confidence": 0.0,
                "objections": objections + ["Hypothesis failed to explain high success rate."]
            }, commit_msg="Reflection: Hypothesis falsified.")
            return

        try:
            first_seen = datetime.fromisoformat(ctx['first_observed_at'])
            last_seen = datetime.fromisoformat(stats['last_seen'])
        except (ValueError, KeyError, TypeError):
            first_seen = datetime.now()
            last_seen = datetime.now()
        
        ready = (confidence >= self.policy.ready_threshold and 
                 (last_seen - first_seen) >= self.policy.observation_window and
                 len(objections) < 2)

        # 2.8: Generative Rationale (Pre-LLM Synthesis)
        success_rate = (new_successes / total_observations) * 100 if total_observations > 0 else 0
        stability = "stable" if confidence > 0.7 else "emerging" if confidence > 0.3 else "volatile"
        
        new_evidence_ids = list(set(ctx.get('evidence_event_ids', []) + stats['all_ids']))
        
        factual_rationale = (
            f"Pattern recognized in {data['context'].get('target', 'unknown')}. "
            f"Success rate: {success_rate:.1f}% over {total_observations:.0f} observations. "
            f"Current state is {stability} with confidence {confidence:.2f}. "
            f"Evidence backed by {len(new_evidence_ids)} episodic events."
        )

        # Try to update procedural steps if they are missing
        new_procedural = ctx.get('procedural')
        if not new_procedural or not new_procedural.get('steps'):
             distiller = DistillationEngine(self.episodic)
             recent_events = self.episodic.query(limit=100, after_id=min(stats['all_ids'])-1 if stats['all_ids'] else 0, order='ASC')
             target_events = [e for e in recent_events if e['id'] in stats['all_ids']]
             if target_events:
                  temp_prop = distiller._create_procedural_proposal(target_events[:-1], target_events[-1])
                  new_procedural = temp_prop.procedural.model_dump() if hasattr(temp_prop.procedural, 'model_dump') else temp_prop.procedural

        self.processor.update_decision(fid, {
            "confidence": round(confidence, 2),
            "hit_count": new_errors,
            "miss_count": new_successes,
            "objections": list(set(objections)),
            "ready_for_review": ready,
            "rationale": factual_rationale,
            "procedural": new_procedural, # ОБНОВЛЯЕМ ШАГИ
            "evidence_event_ids": new_evidence_ids,
            "counter_evidence_event_ids": list(set(ctx.get('counter_evidence_event_ids', []) + [e['id'] for e in stats['success_events']]))
        }, commit_msg=f"Reflection: Epistemic update. Confidence: {confidence:.2f}")

    def _generate_competing_hypotheses(self, target: str, stats: Dict[str, Any]) -> List[str]:
        # 2.9.5: Try to distill procedural steps for these hypotheses
        distiller = DistillationEngine(self.episodic)
        recent_events = self.episodic.query(limit=100, after_id=min(stats['all_ids'])-1 if stats['all_ids'] else 0, order='ASC')
        target_events = [e for e in recent_events if e['id'] in stats['all_ids']]
        
        procedural = None
        if target_events:
            temp_prop = distiller._create_procedural_proposal(target_events[:-1], target_events[-1])
            procedural = temp_prop.procedural

        h1 = ProposalContent(
            title=f"Structural flaw in {target}",
            target=target,
            rationale=f"Consistent failures suggest a missing logical constraint.",
            confidence=0.5,
            strengths=["Explains repeated errors"],
            evidence_event_ids=stats['all_ids'],
            procedural=procedural, # Добавляем шаги
            first_observed_at=datetime.now()
        )
        h2 = ProposalContent(
            title=f"Environmental noise in {target}",
            target=target,
            rationale=f"Errors might be due to transient fluctuations.",
            confidence=0.4,
            strengths=["More conservative"],
            evidence_event_ids=stats['all_ids'],
            procedural=procedural, # Добавляем шаги
            first_observed_at=datetime.now()
        )
        fids = []
        for h_ctx in [h1, h2]:
            decision = self.processor.process_event(source="reflection_engine", kind=KIND_PROPOSAL, content=h_ctx.title, context=h_ctx)
            if decision.should_persist:
                fids.append(decision.metadata.get("file_id"))
        return fids

    def _get_all_draft_proposals(self) -> Dict[str, Dict[str, Any]]:
        drafts = {}
        draft_metas = self.semantic.meta.list_draft_proposals()
        for m in draft_metas:
            fid = m['fid']
            try:
                ctx = json.loads(m.get('context_json', '{}'))
                drafts[fid] = {
                    'kind': m.get('kind'),
                    'content': m.get('content'),
                    'timestamp': m.get('timestamp'),
                    'context': ctx
                }
            except Exception: continue
        return drafts

    def _find_proposals_by_target(self, drafts: Dict[str, Dict[str, Any]], target: str) -> List[Tuple[str, Dict[str, Any]]]:
        return [(fid, data) for fid, data in drafts.items() if data.get('context', {}).get('target') == target]

    def _apply_decay(self, fid: str, data: Dict[str, Any]):
        ctx = data['context']
        new_conf = max(0.0, ctx.get('confidence', 0.0) - self.policy.decay_rate)
        if new_conf < self.policy.min_confidence:
            self.processor.update_decision(fid, {"status": ProposalStatus.REJECTED, "confidence": new_conf}, 
                                          commit_msg="Reflection: Hypothesis rejected (decay).")
        else:
            self.processor.update_decision(fid, {"confidence": new_conf}, commit_msg="Reflection: Applied decay.")
