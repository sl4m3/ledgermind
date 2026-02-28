from typing import List, Dict, Any, Optional
import logging
import json
from ledgermind.core.core.schemas import (
    MemoryEvent, ProceduralContent, ProceduralStep, 
    ProposalContent, ProposalStatus, KIND_RESULT, KIND_ERROR
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

    def distill_trajectories(self, limit: int = 200, after_id: Optional[int] = None) -> List[ProposalContent]:
        """
        Groups events by actor-based sessions and distills them into procedural proposals.
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
            # A new user prompt or an explicit new decision marks the end of previous turn
            if ev.get('source') == 'user' or ev.get('kind') == 'decision':
                if current_turn:
                    turns.append(current_turn)
                current_turn = [ev]
            else:
                if current_turn:
                    current_turn.append(ev)
        
        if current_turn:
            turns.append(current_turn)

        # 3. Stitch Turns into Task Trajectories based on shared target
        trajectories = []
        active_trajectories_by_target = {} # target -> list of turns
        
        RU_SUCCESS_KEYWORDS = {"успешно", "прошли", "исправлено", "завершено", "выполнено"}

        for turn in turns:
            # Detect target for the turn
            target = 'unknown'
            is_success = False
            
            for ev in turn:
                ctx = ev.get('context', {})
                # Target discovery
                candidate = ctx.get('target')
                
                # Try to extract target from commit message or files if not explicitly set
                if (not candidate or candidate == 'unknown') and ev.get('kind') == 'commit_change':
                    content = ev.get('content', '')
                    import re
                    match = re.search(r'\(([^)]+)\):', content)
                    if match:
                        candidate = match.group(1)
                    else:
                        changed_files = ctx.get('changed_files', [])
                        if changed_files:
                            paths = [f.split('/')[0] for f in changed_files if '/' in f]
                            if not paths: paths = [f.split('.')[0] for f in changed_files]
                            if paths:
                                from collections import Counter
                                candidate = Counter(paths).most_common(1)[0][0]

                if candidate and candidate != 'unknown' and len(str(candidate)) > 2:
                    target = candidate
                
                # Success discovery
                if ev.get('kind') == KIND_RESULT:
                    content = ev.get('content', '').lower()
                    if ctx.get('success') or any(kw in content for kw in RU_SUCCESS_KEYWORDS) or "success" in content:
                        is_success = True

            if (not target or target == 'unknown') and active_trajectories_by_target:
                # Inherit target from most recent active trajectory
                target = list(active_trajectories_by_target.keys())[-1]

            if target not in active_trajectories_by_target:
                active_trajectories_by_target[target] = []
            
            active_trajectories_by_target[target].extend(turn)
            
            # If success detected, crystallize this trajectory
            if is_success and target != 'unknown':
                full_events = active_trajectories_by_target.pop(target)
                proposal = self._create_procedural_proposal(full_events, target)
                if proposal:
                    trajectories.append(proposal)
        
        return trajectories

    def _create_procedural_proposal(self, full_events: List[Dict[str, Any]], target: str) -> Optional[ProposalContent]:
        """Creates a Proposal based on a chain of events spanning one or more sessions."""
        steps = []
        evidence_ids = []
        
        def clean_content(content):
            if content.strip().startswith('{'):
                try:
                    data = json.loads(content)
                    return data.get('prompt') or data.get('prompt_response') or content
                except: pass
            return content

        for ev in full_events:
            kind = ev.get('kind')
            # Only include meaningful actions in the procedural steps
            if kind in ['task', 'call', 'commit_change', 'prompt', 'result', 'decision']:
                content = clean_content(ev.get('content', ''))
                if not content or len(content) < 5: continue

                ctx = ev.get('context', {})
                raw_rationale = ctx.get('rationale') or ctx.get('full_message')
                changed_files = ctx.get('changed_files', [])
                
                if not raw_rationale:
                    if kind == 'prompt':
                        raw_rationale = f"User initiative: {content[:3000]}"
                        if len(content) > 3000: raw_rationale += "..."
                    elif kind in ('result', 'decision'):
                        raw_rationale = "System outcome or decision state"
                    elif kind == 'commit_change':
                        raw_rationale = content[:3000]
                        if len(content) > 3000: raw_rationale += "..."
                        if changed_files:
                            raw_rationale += f"\nFiles: {', '.join(changed_files)}"
                    else:
                        raw_rationale = f"Action: {kind}"

                action_text = f"[{kind.upper()}] {content[:3000]}"
                if len(content) > 3000: action_text += "..."
                
                if kind == 'commit_change':
                    commit_hash = ctx.get('hash', 'unknown')[:8]
                    action_text = f"[COMMIT] {commit_hash}: {content[:3000]}"
                    if len(content) > 3000: action_text += "..."

                steps.append(ProceduralStep(
                    action=action_text,
                    rationale=raw_rationale
                ))
                evidence_ids.append(ev.get('id', 0))

        if not steps:
            return None

        last_id = evidence_ids[-1] if evidence_ids else 0
        procedural = ProceduralContent(
            steps=steps,
            target_task=target,
            success_evidence_ids=evidence_ids
        )

        title = f"Procedural Optimization for {target}"
        rationale = f"Distilled from multi-turn successful trajectory (ending at ID {last_id})"

        return ProposalContent(
            title=title,
            target=target,
            status=ProposalStatus.DRAFT,
            rationale=rationale,
            keywords=self._extract_keywords(title, target, rationale),
            confidence=0.85, # Increased confidence for multi-session patterns
            evidence_event_ids=evidence_ids,
            procedural=procedural,
            enrichment_status="pending"
        )
