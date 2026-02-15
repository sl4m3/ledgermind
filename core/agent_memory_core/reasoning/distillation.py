from typing import List, Dict, Any, Optional
import logging
from agent_memory_core.core.schemas import (
    MemoryEvent, ProceduralContent, ProceduralStep, 
    ProposalContent, ProposalStatus, KIND_RESULT, KIND_ERROR
)

logger = logging.getLogger(__name__)

class DistillationEngine:
    """
    Реализация принципа MemP: Дистилляция траекторий в процедурные знания.
    Анализирует эпизодическую память для выделения успешных паттернов действий.
    """
    
    def __init__(self, episodic_store):
        self.episodic = episodic_store

    def distill_trajectories(self, limit: int = 100) -> List[ProposalContent]:
        """
        Ищет успешные цепочки событий и превращает их в предложения по процедурам.
        """
        # query возвращает события в порядке убывания времени (DESC)
        events = self.episodic.query(limit=limit, status='active')
        if not events:
            return []

        # Переворачиваем, чтобы идти от прошлого к настоящему
        chronological_events = list(reversed(events))
        proposals = []
        
        for i, event in enumerate(chronological_events):
            if event.get('kind') == KIND_RESULT:
                context = event.get('context', {})
                if context.get('success') or "success" in event.get('content', '').lower():
                    # Траектория - это события ПЕРЕД текущим результатом
                    # Берем окно из последних 5 событий
                    trajectory_events = chronological_events[max(0, i-5):i]
                    if trajectory_events:
                        proposal = self._create_procedural_proposal(trajectory_events, event)
                        proposals.append(proposal)
        
        return proposals

    def _create_procedural_proposal(self, trajectory: List[Dict[str, Any]], result_event: Dict[str, Any]) -> ProposalContent:
        """Создает Proposal на основе цепочки событий."""
        steps = []
        evidence_ids = []
        
        for ev in trajectory:
            # Нас интересуют действия и задачи
            if ev.get('kind') in ['task', 'call', 'decision']:
                steps.append(ProceduralStep(
                    action=ev.get('content', 'Action'),
                    rationale=ev.get('context', {}).get('rationale')
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
