from typing import List, Dict, Any, Optional
import logging
import json
from ledgermind.core.core.schemas import (
    MemoryEvent, ProposalContent, ProposalStatus, KIND_RESULT, KIND_ERROR
)

logger = logging.getLogger(__name__)

class DistillationEngine:
    """
    Distillation Engine v5.1: Session-based Trajectory Distiller.
    Implementation of the MemP principle: distilling active trajectories into procedural knowledge.
    
    Now supports multi-turn session boundaries (user -> agent -> user) and target-based stitching.
    """
    
    def __init__(self, episodic_store, window_size: int = 20):
        self.episodic = episodic_store
        self.window_size = window_size # Now acts as a search depth for multi-session stitching

    def _extract_keywords(self, title: str, target: str, rationale: str) -> List[str]:
        """Simple keyword extraction from text fields."""
        import re
        all_text = f"{title} {target} {rationale}".lower()
        words = re.findall(r'[a-zа-я0-9]{3,}', all_text)
        stop_words = {"for", "the", "and", "with", "from", "this", "that", "was", "were", "been", "has", "had", 
                      "для", "или", "это", "был", "была", "было", "были", "его", "ее", "их", "как", "мне"}
        unique_words = list(set(w for w in words if w not in stop_words))
        return sorted(unique_words)[:10]

    def _infer_sub_target(self, event: Dict[str, Any]) -> str:
        """Infers the logical sub-target or intent from event content and context."""
        content = event.get('content', '').lower()
        kind = event.get('kind', '').lower()
        source = event.get('source', '').lower()
        
        # 1. Direct hints in kind/source
        if kind == 'reflection_summary' or source == 'reflection_engine': return 'reflection'
        if 'enrich' in content or 'enrich' in kind: return 'enrichment'
        if 'distill' in content or 'distill' in kind: return 'distillation'
        
        # 2. Keywords in content
        keywords = {
            'worker': ['worker', 'background', 'task_queue', 'celery', 'pkill'],
            'mcp': ['mcp', 'tools', 'specification', 'contract'],
            'lifecycle': ['lifecycle', 'vitality', 'decay', 'promote'],
            'storage': ['sqlite', 'episodic', 'semantic', 'migration', 'db_path'],
            'reasoning': ['reasoning', 'inference', 'llm', 'prompt', 'synthesis'],
            'server': ['server', 'gateway', 'health', 'metrics', 'http']
        }
        
        for sub, kws in keywords.items():
            if any(kw in content for kw in kws):
                return sub
                
        # 3. Path-based inference (if commit)
        ctx = event.get('context', {})
        changed_files = ctx.get('changed_files', [])
        for f in changed_files:
            f_lower = f.lower()
            if 'reflection' in f_lower: return 'reflection'
            if 'enrich' in f_lower: return 'enrichment'
            if 'distill' in f_lower: return 'distillation'
            if 'worker' in f_lower or 'background' in f_lower: return 'worker'
            if 'server' in f_lower or 'gateway' in f_lower: return 'server'
            if 'store' in f_lower: return 'storage'
            
        return 'general'

    def distill_trajectories(self, limit: int = 200, after_id: Optional[int] = None) -> List[ProposalContent]:
        """
        Groups events by actor-based sessions and distills them into procedural proposals.
        Splits by (target, sub_target) to ensure granularity.
        """
        # 1. Fetch events
        order = 'ASC' if after_id is not None else 'DESC'
        events = self.episodic.query(limit=limit, status='active', after_id=after_id, order=order)
        if not events:
            return []

        chronological_events = list(reversed(events)) if order == 'DESC' else events
        
        # 2. Group events into Turns (User Prompt -> Agent Chain)
        turns = []
        current_turn = []
        
        for ev in chronological_events:
            if ev.get('source') == 'user' or ev.get('kind') == 'decision':
                if current_turn:
                    turns.append(current_turn)
                current_turn = [ev]
            else:
                if current_turn:
                    current_turn.append(ev)
        
        if current_turn:
            turns.append(current_turn)

        # 3. Stitch Turns into Task Trajectories based on shared (target, sub_target)
        trajectories = []
        active_trajectories = {} # (target, sub_target) -> list of turns
        
        RU_SUCCESS_KEYWORDS = {"успешно", "прошли", "исправлено", "завершено", "выполнено"}

        for turn in turns:
            target = 'unknown'
            sub_target = 'general'
            is_success = False
            
            # Identify most specific target and sub_target in the turn
            for ev in turn:
                ctx = ev.get('context', {})
                candidate_target = ctx.get('target')
                
                # Target discovery logic
                if (not candidate_target or candidate_target == 'unknown') and ev.get('kind') == 'commit_change':
                    content = ev.get('content', '')
                    import re
                    match = re.search(r'\(([^)]+)\):', content)
                    if match: candidate_target = match.group(1)
                    else:
                        changed_files = ctx.get('changed_files', [])
                        if changed_files:
                            paths = [f.split('/')[0] for f in changed_files if '/' in f]
                            if not paths: paths = [f.split('.')[0] for f in changed_files]
                            if paths:
                                from collections import Counter
                                candidate_target = Counter(paths).most_common(1)[0][0]

                if candidate_target and candidate_target != 'unknown' and len(str(candidate_target)) > 2:
                    target = candidate_target
                
                # Sub-target discovery (new logic)
                candidate_sub = self._infer_sub_target(ev)
                if candidate_sub != 'general':
                    sub_target = candidate_sub

                # Success discovery
                if ev.get('kind') == KIND_RESULT:
                    content = ev.get('content', '').lower()
                    if ctx.get('success') or any(kw in content for kw in RU_SUCCESS_KEYWORDS) or "success" in content:
                        is_success = True

            # Use (target, sub_target) as key
            cluster_key = (target, sub_target)

            if cluster_key not in active_trajectories:
                active_trajectories[cluster_key] = []
            
            active_trajectories[cluster_key].extend(turn)
            
            if is_success and target != 'unknown':
                full_events = active_trajectories.pop(cluster_key)
                
                # Create final target name like "core/reflection"
                composite_target = target if sub_target == 'general' else f"{target}/{sub_target}"
                proposal = self._create_trajectory_proposal(full_events, composite_target)
                if proposal:
                    trajectories.append(proposal)
        
        return trajectories

    def _create_trajectory_proposal(self, full_events: List[Dict[str, Any]], target: str) -> Optional[ProposalContent]:
        """Creates a Proposal based on a chain of events spanning one or more sessions."""
        evidence_ids = []
        
        for ev in full_events:
            kind = ev.get('kind')
            if kind in ['task', 'call', 'commit_change', 'prompt', 'result', 'decision', 'error']:
                evidence_ids.append(ev.get('id', 0))

        if not evidence_ids:
            return None

        last_id = evidence_ids[-1] if evidence_ids else 0
        title = f"Trajectory Synthesis for {target}"
        rationale = f"Observed successful execution trajectory for '{target}' (terminating at ID {last_id}). Analysis of raw logs is required to promote this to procedural knowledge."

        return ProposalContent(
            title=title,
            target=target,
            status=ProposalStatus.DRAFT,
            rationale=rationale,
            keywords=self._extract_keywords(title, target, rationale),
            confidence=0.85,
            evidence_event_ids=evidence_ids,
            enrichment_status="pending"
        )
