from typing import List, Dict, Any, Optional
import logging
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
        
        for ev in trajectory:
            # Нас интересуют действия, задачи и изменения кода
            if ev.get('kind') in ['task', 'call', 'decision', 'commit_change']:
                steps.append(ProceduralStep(
                    action=ev.get('content', 'Action'),
                    rationale=ev.get('context', {}).get('rationale') or ev.get('context', {}).get('full_message')
                ))
                evidence_ids.append(ev.get('id', 0))

        target = result_event.get('context', {}).get('target', 'general_task')
        
        # Если шагов не нашлось, все равно добавим результат как улику
        evidence_ids.append(result_event.get('id', 0))

        procedural = ProceduralContent(
            steps=steps,
            target_task=target,
            success_evidence_ids=evidence_ids
        )

        return ProposalContent(
            title=f"Procedural Optimization for {target}",
            target=target,
            status=ProposalStatus.DRAFT,
            rationale=f"Distilled from successful trajectory ending in event {result_event.get('id')}",
            confidence=0.8,
            evidence_event_ids=evidence_ids,
            procedural=procedural
        )
