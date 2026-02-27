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
    Реализация принципа MemP: Дистилляция траекторий в процедурные знания.
    Анализирует эпизодическую память для выделения успешных паттернов действий.
    """
    
    def __init__(self, episodic_store, window_size: int = 5):
        self.episodic = episodic_store
        self.window_size = window_size

    def _extract_keywords(self, title: str, target: str, rationale: str) -> List[str]:
        """Simple keyword extraction from text fields."""
        import re
        all_text = f"{title} {target} {rationale}".lower()
        words = re.findall(r'[a-zа-я0-9]{3,}', all_text)
        stop_words = {"for", "the", "and", "with", "from", "this", "that", "was", "were", "been", "has", "had", 
                      "для", "или", "это", "был", "была", "было", "были", "его", "ее", "их"}
        unique_words = list(set(w for w in words if w not in stop_words))
        return sorted(unique_words)[:10]

    def distill_trajectories(self, limit: int = 100, after_id: Optional[int] = None) -> List[ProposalContent]:
        """
        Ищет успешные цепочки событий и превращает их в предложения по процедурам.
        """
        # Если есть after_id, идем по порядку (ASC), если нет - берем последние (DESC)
        order = 'ASC' if after_id is not None else 'DESC'
        events = self.episodic.query(limit=limit, status='active', after_id=after_id, order=order)
        if not events:
            return []

        # Если брали DESC, переворачиваем для хронологии. Если ASC - уже ок.
        chronological_events = list(reversed(events)) if order == 'DESC' else events
        proposals = []
        
        for i, event in enumerate(chronological_events):
            if event.get('kind') == KIND_RESULT:
                context = event.get('context', {})
                if context.get('success') or "success" in event.get('content', '').lower():
                    # Траектория - это события ПЕРЕД текущим результатом
                    # Берем окно из последних событий
                    trajectory_events = chronological_events[max(0, i - self.window_size):i]
                    if trajectory_events:
                        proposal = self._create_procedural_proposal(trajectory_events, event)
                        proposals.append(proposal)
        
        return proposals

    def _create_procedural_proposal(self, trajectory: List[Dict[str, Any]], result_event: Dict[str, Any]) -> ProposalContent:
        """Создает Proposal на основе цепочки событий."""
        steps = []
        evidence_ids = []
        
        def clean_content(content):
            # Если это JSON (как в наших промптах), достаем только само сообщение
            if content.strip().startswith('{'):
                try:
                    data = json.loads(content)
                    return data.get('prompt') or data.get('prompt_response') or content
                except: pass
            return content

        for ev in trajectory:
            kind = ev.get('kind')
            # Расширяем список учитываемых событий
            if kind in ['task', 'call', 'decision', 'commit_change', 'prompt', 'result']:
                content = clean_content(ev.get('content', ''))
                if not content or len(content) < 5: continue

                # Improved Rationale Extraction
                ctx = ev.get('context', {})
                raw_rationale = ctx.get('rationale') or ctx.get('full_message')
                changed_files = ctx.get('changed_files', [])
                
                if not raw_rationale:
                    if kind == 'prompt':
                        raw_rationale = f"User initiative: {content[:100]}..."
                    elif kind == 'result':
                        raw_rationale = "System response/outcome of action"
                    elif kind == 'commit_change':
                        raw_rationale = content[:150]
                        if changed_files:
                            file_str = ", ".join(changed_files[:5])
                            if len(changed_files) > 5:
                                file_str += f" (+{len(changed_files)-5} more)"
                            raw_rationale += f" | Changes: {file_str}"
                    else:
                        raw_rationale = f"Recorded {kind} event"

                action_text = f"[{kind.upper()}] {content[:200]}..."
                if kind == 'commit_change':
                    commit_hash = ctx.get('hash', 'unknown')[:8]
                    if changed_files:
                        file_summary = ", ".join(changed_files[:3])
                        action_text = f"[{kind.upper()}] {commit_hash}: {content[:150]}... (Files: {file_summary})"
                    else:
                        action_text = f"[{kind.upper()}] {commit_hash}: {content[:150]}..."

                steps.append(ProceduralStep(
                    action=action_text,
                    rationale=raw_rationale
                ))
                evidence_ids.append(ev.get('id', 0))

        target = result_event.get('context', {}).get('target')
        
        # Target Inheritance: If result has no target, look back in trajectory
        if not target or target == 'unknown':
            for ev in reversed(trajectory):
                candidate = ev.get('context', {}).get('target')
                if candidate and candidate != 'unknown':
                    target = candidate
                    break
        
        target = target or 'unknown'
        
        # Если шагов не нашлось, все равно добавим результат как улику
        evidence_ids.append(result_event.get('id', 0))

        procedural = ProceduralContent(
            steps=steps,
            target_task=target,
            success_evidence_ids=evidence_ids
        )

        title = f"Procedural Optimization for {target}"
        rationale = f"Distilled from successful trajectory ending in event {result_event.get('id')}"

        return ProposalContent(
            title=title,
            target=target,
            status=ProposalStatus.DRAFT,
            rationale=rationale,
            keywords=self._extract_keywords(title, target, rationale),
            confidence=0.8,
            evidence_event_ids=evidence_ids,
            procedural=procedural
        )
