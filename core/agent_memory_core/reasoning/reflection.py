import logging
import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from agent_memory_core.core.schemas import (
    MemoryEvent, KIND_PROPOSAL, ProposalContent, ProposalStatus, 
    KIND_RESULT, KIND_ERROR
)
from agent_memory_core.stores.episodic import EpisodicStore
from agent_memory_core.stores.semantic import SemanticStore
from agent_memory_core.reasoning.distillation import DistillationEngine

logger = logging.getLogger(__name__)

class ReflectionPolicy:
    def __init__(self, 
                 error_threshold: int = 3, 
                 min_confidence: float = 0.3,
                 observation_window_hours: int = 12,
                 decay_rate: float = 0.05,
                 ready_threshold: float = 0.8):
        self.error_threshold = error_threshold
        self.min_confidence = min_confidence
        self.observation_window = timedelta(hours=observation_window_hours)
        self.decay_rate = decay_rate
        self.ready_threshold = ready_threshold

class ReflectionEngine:
    """
    Reflection Engine v4: Competitive Hypotheses & Scientific Falsification.
    No longer just counts errors; it pits explanations against each other.
    """
    def __init__(self, episodic_store: EpisodicStore, semantic_store: SemanticStore, policy: Optional[ReflectionPolicy] = None):
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.policy = policy or ReflectionPolicy()

    def run_cycle(self) -> List[str]:
        logger.info("Starting competitive reflection cycle (v4)...")
        
        # 0. Distillation (MemP Ground Truth)
        distiller = DistillationEngine(self.episodic)
        procedural_proposals = distiller.distill_trajectories()
        result_ids = []
        
        for prop in procedural_proposals:
            event = MemoryEvent(source="reflection_engine", kind=KIND_PROPOSAL, content=prop.title, context=prop)
            result_ids.append(self.semantic.save(event))

        # 1. Evidence Aggregation
        recent_events = self.episodic.query(limit=1000, status='active')
        evidence_clusters = self._cluster_evidence(recent_events)
        
        all_drafts = self._get_all_draft_proposals()
        processed_fids = set()
        
        # 2. Update and Falsify existing hypotheses
        for target, stats in evidence_clusters.items():
            relevant_proposals = self._find_proposals_by_target(all_drafts, target)
            
            for fid, data in relevant_proposals:
                self._evaluate_hypothesis(fid, data, stats)
                processed_fids.add(fid)
                result_ids.append(fid)
            
            # 3. Generate new hypotheses if threshold met and no active strong hypo
            if stats['errors'] >= self.policy.error_threshold and not any(p[1]['context']['confidence'] > 0.7 for p in relevant_proposals):
                new_fids = self._generate_competing_hypotheses(target, stats)
                result_ids.extend(new_fids)

        # 4. Global Competition & Decay
        for fid, data in all_drafts.items():
            if fid not in processed_fids:
                self._apply_decay(fid, data)
                
        return result_ids

    def _cluster_evidence(self, events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        clusters = {}
        for ev in events:
            ctx = ev.get('context', {})
            target = ctx.get('target') or "general"
            
            if target not in clusters:
                clusters[target] = {
                    'errors': 0, 'successes': 0, 
                    'error_events': [], 'success_events': [],
                    'last_seen': ev['timestamp']
                }
            
            if ev['kind'] == KIND_ERROR:
                clusters[target]['errors'] += 1
                clusters[target]['error_events'].append(ev)
            elif ev['kind'] == KIND_RESULT:
                clusters[target]['successes'] += 1
                clusters[target]['success_events'].append(ev)
                
            try:
                clusters[target]['last_seen'] = max(clusters[target]['last_seen'], ev['timestamp'])
            except: pass
        return clusters

    def _evaluate_hypothesis(self, fid: str, data: Dict[str, Any], stats: Dict[str, Any]):
        """
        Evaluates a hypothesis against new evidence using scientific falsification.
        Successes in the same target area act as strong objections.
        """
        ctx = data['context']
        
        # 1. Collect Evidence vs Objections
        new_errors = ctx.get('hit_count', 0) + stats['errors']
        new_successes = ctx.get('miss_count', 0) + stats['successes']
        
        objections = list(set(ctx.get('objections', [])))
        if stats['successes'] > 0:
            objections.append(f"Falsification Signal: {stats['successes']} successes observed in target area.")
        
        # 2. Epistemic Confidence (Bayesian-ish)
        # We penalize inconsistency (mix of errors and successes)
        total_observations = new_errors + new_successes
        if total_observations == 0: return
        
        # Formula: Confidence drops sharply if successes are present
        base_rate = new_errors / total_observations
        epistemic_penalty = (new_successes * 2) / (new_errors + 1)
        confidence = max(0.0, base_rate - epistemic_penalty)
        
        # 3. Scientific Falsification
        # If confidence hits 0 or successes significantly outweigh errors, kill the hypothesis
        if confidence <= 0.05 and new_successes > new_errors:
            self.semantic.update_decision(fid, {
                "status": ProposalStatus.FALSIFIED,
                "confidence": 0.0,
                "objections": objections + ["Hypothesis failed to explain high success rate."]
            }, commit_msg="Reflection: Hypothesis falsified by contradictory evidence.")
            return

        first_seen = datetime.fromisoformat(ctx['first_observed_at'])
        last_seen = datetime.fromisoformat(stats['last_seen'])
        
        # Readiness requires high confidence AND sufficient observation time AND low objection count
        ready = (confidence >= self.policy.ready_threshold and 
                 (last_seen - first_seen) >= self.policy.observation_window and
                 len(objections) < 2)

        self.semantic.update_decision(fid, {
            "confidence": round(confidence, 2),
            "hit_count": new_errors,
            "miss_count": new_successes,
            "objections": list(set(objections)),
            "ready_for_review": ready,
            "counter_evidence_event_ids": list(set(ctx.get('counter_evidence_event_ids', []) + [e['id'] for e in stats['success_events']]))
        }, commit_msg=f"Reflection: Epistemic update. Confidence: {confidence:.2f}")

    def _generate_competing_hypotheses(self, target: str, stats: Dict[str, Any]) -> List[str]:
        """
        Generates at least two competing explanations for the observed failures.
        """
        # H1: The "Causal" Hypothesis (Assumption of a logical flaw)
        h1 = ProposalContent(
            title=f"Structural flaw in {target}",
            target=target,
            rationale=f"Consistent failures ({stats['errors']}) suggest a missing logical constraint.",
            confidence=0.5,
            strengths=["Explains repeated errors", "Provides actionable fix"],
            objections=["Doesn't explain transient successes if any"],
            evidence_event_ids=[e['id'] for e in stats['error_events']],
            first_observed_at=datetime.now()
        )
        
        # H2: The "Environmental" Hypothesis (Assumption of transient/noise issues)
        h2 = ProposalContent(
            title=f"Environmental noise in {target}",
            target=target,
            rationale=f"Errors might be due to transient fluctuations, not logical flaws.",
            confidence=0.4,
            strengths=["More conservative", "Prevents over-engineering"],
            objections=["Harder to prove", "Doesn't provide an immediate fix"],
            evidence_event_ids=[e['id'] for e in stats['error_events']],
            first_observed_at=datetime.now()
        )

        fids = []
        for h_ctx in [h1, h2]:
            event = MemoryEvent(source="reflection_engine", kind=KIND_PROPOSAL, content=h_ctx.title, context=h_ctx)
            fids.append(self.semantic.save(event))
        
        # Cross-link them as alternatives
        for fid in fids:
            alts = [f for f in fids if f != fid]
            self.semantic.update_decision(fid, {"alternative_ids": alts}, commit_msg="Reflection: Linking competing hypotheses.")
            
        return fids

    def _get_all_draft_proposals(self) -> Dict[str, Dict[str, Any]]:
        drafts = {}
        from agent_memory_core.stores.semantic_store.loader import MemoryLoader
        for fid in self.semantic.list_decisions():
            try:
                with open(os.path.join(self.semantic.repo_path, fid), 'r') as f:
                    data, _ = MemoryLoader.parse(f.read())
                    if data.get('kind') == KIND_PROPOSAL and data.get('context', {}).get('status') in [ProposalStatus.DRAFT]:
                        drafts[fid] = data
            except: continue
        return drafts

    def _find_proposals_by_target(self, drafts: Dict[str, Dict[str, Any]], target: str) -> List[Tuple[str, Dict[str, Any]]]:
        return [(fid, data) for fid, data in drafts.items() if data.get('context', {}).get('target') == target]

    def _apply_decay(self, fid: str, data: Dict[str, Any]):
        ctx = data['context']
        new_conf = max(0.0, ctx.get('confidence', 0.0) - self.policy.decay_rate)
        if new_conf < self.policy.min_confidence:
            self.semantic.update_decision(fid, {"status": ProposalStatus.REJECTED, "confidence": new_conf}, 
                                          commit_msg="Reflection: Hypothesis rejected due to lack of new evidence.")
        else:
            self.semantic.update_decision(fid, {"confidence": new_conf}, commit_msg="Reflection: Applied decay.")
