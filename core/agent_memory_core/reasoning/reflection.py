import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from agent_memory_core.core.schemas import MemoryEvent, KIND_PROPOSAL, ProposalContent, ProposalStatus, KIND_RESULT, KIND_ERROR
from agent_memory_core.stores.episodic import EpisodicStore
from agent_memory_core.stores.semantic import SemanticStore
from agent_memory_core.reasoning.distillation import DistillationEngine

logger = logging.getLogger(__name__)

class ReflectionPolicy:
    def __init__(self, 
                 error_threshold: int = 3, 
                 min_confidence: float = 0.4,
                 observation_window_hours: int = 12,
                 decay_rate: float = 0.05,
                 ready_threshold: float = 0.85):
        self.error_threshold = error_threshold
        self.min_confidence = min_confidence
        self.observation_window = timedelta(hours=observation_window_hours)
        self.decay_rate = decay_rate
        self.ready_threshold = ready_threshold

class ReflectionEngine:
    """
    Reflection Engine v3: Competitive Hypotheses & Falsification.
    """
    def __init__(self, episodic_store: EpisodicStore, semantic_store: SemanticStore, policy: Optional[ReflectionPolicy] = None):
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.policy = policy or ReflectionPolicy()

    def run_cycle(self) -> List[str]:
        logger.info("Starting competitive reflection cycle...")
        
        # 0. Distillation (MemP)
        distiller = DistillationEngine(self.episodic)
        procedural_proposals = distiller.distill_trajectories()
        result_ids = []
        
        for prop in procedural_proposals:
            event = MemoryEvent(source="reflection_engine", kind=KIND_PROPOSAL, content=prop.title, context=prop)
            result_ids.append(self.semantic.save(event))

        # 1. Pattern Analysis with Falsification Support
        recent_events = self.episodic.query(limit=1000, status='active')
        patterns = self._analyze_patterns(recent_events)
        
        all_drafts = self._get_all_draft_proposals()
        processed_ids = set()
        
        # 2. Competitive Hypothesis Selection
        for target, stats in patterns.items():
            existing_id = self._find_proposal_by_target(all_drafts, target)
            
            if existing_id:
                # Update with Falsification logic: successes lower confidence
                self._update_proposal(existing_id, all_drafts[existing_id], stats)
                processed_ids.add(existing_id)
                result_ids.append(existing_id)
            elif stats['errors'] >= self.policy.error_threshold:
                # Create initial competitive proposals (In v3 we create one balanced proposal)
                new_id = self._create_proposal(target, stats)
                if new_id: result_ids.append(new_id)

        # 3. Doubt Mechanism (Decay)
        for fid, data in all_drafts.items():
            if fid not in processed_ids:
                self._apply_decay(fid, data)
                
        return result_ids

    def _analyze_patterns(self, events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        patterns = {}
        for ev in events:
            ctx = ev.get('context', {})
            target = ctx.get('target') or "general"
            
            if target not in patterns:
                patterns[target] = {'errors': 0, 'successes': 0, 'evidence': [], 'last_seen': ev['timestamp']}
            
            if ev['kind'] == KIND_ERROR:
                patterns[target]['errors'] += 1
                patterns[target]['evidence'].append(ev['id'])
            elif ev['kind'] == KIND_RESULT:
                patterns[target]['successes'] += 1
                
            try:
                patterns[target]['last_seen'] = max(patterns[target]['last_seen'], ev['timestamp'])
            except: pass
        return patterns

    def _calculate_competitive_confidence(self, errors: int, successes: int) -> float:
        """
        Falsification logic: 
        Confidence grows with errors but is severely PENALIZED by successes in the same area.
        """
        if errors == 0: return 0.0
        
        # Base confidence from error frequency
        base = min(0.9, errors / (errors + 2))
        
        # Falsification penalty: if we have successes, maybe the "problem" isn't a rule issue
        penalty = (successes / (errors + successes)) if (errors + successes) > 0 else 0
        
        return max(0.0, base - (penalty * 0.5))

    def _update_proposal(self, fid: str, data: Dict[str, Any], stats: Dict[str, Any]):
        ctx = data['context']
        new_errors = ctx.get('hit_count', 0) + stats['errors']
        new_successes = ctx.get('miss_count', 0) + stats['successes']
        
        confidence = self._calculate_competitive_confidence(new_errors, new_successes)
        
        # Stability check (Review Window)
        first_seen = datetime.fromisoformat(ctx['first_observed_at'])
        last_seen = datetime.fromisoformat(stats['last_seen'])
        observation_duration = last_seen - first_seen
        
        ready = (confidence >= self.policy.ready_threshold and 
                 observation_duration >= self.policy.observation_window)

        # Log falsification attempt
        msg = f"Reflection: Updated. Confidence: {confidence:.2f}"
        if stats['successes'] > 0:
            msg += f" (Falsification signal: observed {stats['successes']} successes)"

        self.semantic.update_decision(fid, {
            "confidence": confidence,
            "hit_count": new_errors,
            "miss_count": new_successes,
            "last_observed_at": stats['last_seen'],
            "evidence_event_ids": list(set(ctx.get('evidence_event_ids', []) + stats['evidence'])),
            "ready_for_review": ready
        }, commit_msg=msg)

    def _create_proposal(self, target: str, stats: Dict[str, Any]) -> str:
        if len(stats.get('evidence', [])) < 3:
            return ""

        confidence = self._calculate_competitive_confidence(stats['errors'], stats['successes'])
        active_decisions = self.semantic.list_active_conflicts(target)
        
        proposal_ctx = ProposalContent(
            title=f"Stability optimization for {target}",
            target=target,
            status=ProposalStatus.DRAFT,
            rationale=f"Observed {stats['errors']} errors. Competitive analysis shows {stats['successes']} successes in same area.",
            confidence=confidence,
            evidence_event_ids=stats['evidence'],
            suggested_supersedes=active_decisions,
            hit_count=stats['errors'],
            miss_count=stats['successes'],
            first_observed_at=datetime.now(),
            last_observed_at=datetime.now()
        )

        event = MemoryEvent(
            source="reflection_engine",
            kind=KIND_PROPOSAL,
            content=f"Competitive hypothesis for {target}",
            context=proposal_ctx
        )
        return self.semantic.save(event)

    def _get_all_draft_proposals(self) -> Dict[str, Dict[str, Any]]:
        drafts = {}
        from agent_memory_core.stores.semantic_store.loader import MemoryLoader
        for fid in self.semantic.list_decisions():
            try:
                with open(os.path.join(self.semantic.repo_path, fid), 'r') as f:
                    data, _ = MemoryLoader.parse(f.read())
                    if data.get('kind') == KIND_PROPOSAL and data.get('context', {}).get('status') == ProposalStatus.DRAFT:
                        drafts[fid] = data
            except: continue
        return drafts

    def _find_proposal_by_target(self, proposals: Dict[str, Dict[str, Any]], target: str) -> Optional[str]:
        for fid, data in proposals.items():
            if data.get('context', {}).get('target') == target:
                return fid
        return None

    def _apply_decay(self, fid: str, data: Dict[str, Any]):
        ctx = data['context']
        old_conf = ctx.get('confidence', 0.0)
        new_conf = max(0.0, old_conf - self.policy.decay_rate)
        if new_conf < self.policy.min_confidence:
            self.semantic.update_decision(fid, {"status": ProposalStatus.REJECTED, "confidence": new_conf}, 
                                          commit_msg="Reflection: Rejected due to low confidence.")
        else:
            self.semantic.update_decision(fid, {"confidence": new_conf}, commit_msg=f"Reflection: Applied decay.")
