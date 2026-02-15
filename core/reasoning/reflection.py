import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from core.schemas import MemoryEvent, KIND_PROPOSAL, ProposalContent, ProposalStatus, KIND_RESULT, KIND_ERROR
from stores.episodic import EpisodicStore
from stores.semantic import SemanticStore

logger = logging.getLogger(__name__)

class ReflectionPolicy:
    """Конфигурация правил для Reflection Engine."""
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
    Двигатель саморефлексии v2 (Mature).
    Реализует механизм сомнения, инертности и анализа конфликтов.
    """
    def __init__(self, episodic_store: EpisodicStore, semantic_store: SemanticStore, policy: Optional[ReflectionPolicy] = None):
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.policy = policy or ReflectionPolicy()

    def run_cycle(self) -> List[str]:
        """Запускает цикл анализа."""
        logger.info("Starting mature reflection cycle...")
        # Берем больше событий для анализа баланса успехов и ошибок
        recent_events = self.episodic.query(limit=1000, status='active')
        
        # 1. Группируем события по мишеням (targets)
        patterns = self._analyze_patterns(recent_events)
        
        # 2. Получаем все текущие черновики предложений
        all_proposals = self._get_all_draft_proposals()
        processed_ids = set()
        
        # 3. Обновляем существующие или создаем новые предложения
        result_ids = []
        for target, stats in patterns.items():
            existing_id = self._find_proposal_by_target(all_proposals, target)
            
            if existing_id:
                self._update_proposal(existing_id, all_proposals[existing_id], stats)
                processed_ids.add(existing_id)
                result_ids.append(existing_id)
            elif stats['errors'] >= self.policy.error_threshold:
                new_id = self._create_proposal(target, stats)
                result_ids.append(new_id)

        # 4. Механизм Сомнения: применяем decay к тем, по кому не было новых данных
        for fid, data in all_proposals.items():
            if fid not in processed_ids:
                self._apply_decay(fid, data)
                
        return result_ids

    def _analyze_patterns(self, events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Анализирует баланс ошибок и успехов по целям."""
        patterns = {}
        for ev in events:
            # Пытаемся извлечь target из контекста
            ctx = ev.get('context', {})
            target = ctx.get('target') or "unknown_target"
            
            if target not in patterns:
                patterns[target] = {'errors': 0, 'successes': 0, 'evidence': [], 'last_seen': ev['timestamp']}
            
            if ev['kind'] == KIND_ERROR:
                patterns[target]['errors'] += 1
                patterns[target]['evidence'].append(ev['id'])
            elif ev['kind'] == KIND_RESULT:
                patterns[target]['successes'] += 1
                
            # Обновляем время последнего наблюдения (ISO string to datetime)
            try:
                ev_time = datetime.fromisoformat(ev['timestamp'])
                patterns[target]['last_seen'] = max(patterns[target]['last_seen'], ev['timestamp'])
            except: pass
            
        return patterns

    def _get_all_draft_proposals(self) -> Dict[str, Dict[str, Any]]:
        """Загружает все текущие черновики из семантической памяти."""
        drafts = {}
        from stores.semantic_store.loader import MemoryLoader
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

    def _calculate_confidence(self, hits: int, misses: int) -> float:
        """Более строгая модель: баланс между ошибками и успехами."""
        total = hits + misses
        if total == 0: return 0.0
        # Базовая вероятность + бонус за перевес ошибок
        ratio = hits / total
        # Если успехов много, уверенность падает даже при наличии ошибок
        return min(0.99, ratio * (1.0 - 1.0 / (hits + 1)))

    def _update_proposal(self, fid: str, data: Dict[str, Any], stats: Dict[str, Any]):
        """Обновление с учетом инертности и накопленного опыта."""
        ctx = data['context']
        new_hits = ctx.get('hit_count', 0) + stats['errors']
        new_misses = ctx.get('miss_count', 0) + stats['successes']
        
        confidence = self._calculate_confidence(new_hits, new_misses)
        
        # Проверка инертности
        first_seen = datetime.fromisoformat(ctx['first_observed_at'])
        last_seen = datetime.fromisoformat(stats['last_seen'])
        observation_duration = last_seen - first_seen
        
        ready = (confidence >= self.policy.ready_threshold and 
                 observation_duration >= self.policy.observation_window)

        updates = {
            "confidence": confidence,
            "hit_count": new_hits,
            "miss_count": new_misses,
            "last_observed_at": stats['last_seen'],
            "evidence_event_ids": list(set(ctx.get('evidence_event_ids', []) + stats['evidence'])),
            "ready_for_review": ready
        }
        
        self.semantic.update_decision(fid, updates, commit_msg=f"Reflection: Confidence updated to {confidence:.2f}")

    def _apply_decay(self, fid: str, data: Dict[str, Any]):
        """Механизм Сомнения: уменьшение уверенности при отсутствии данных."""
        ctx = data['context']
        old_conf = ctx.get('confidence', 0.0)
        new_conf = max(0.0, old_conf - self.policy.decay_rate)
        
        if new_conf < self.policy.min_confidence:
            # Если уверенность упала слишком низко, отклоняем гипотезу
            self.semantic.update_decision(fid, {"status": ProposalStatus.REJECTED, "confidence": new_conf}, 
                                          commit_msg="Reflection: Proposal rejected due to low confidence (decay).")
        else:
            self.semantic.update_decision(fid, {"confidence": new_conf}, 
                                          commit_msg=f"Reflection: Applied decay. New confidence: {new_conf:.2f}")

    def _create_proposal(self, target: str, stats: Dict[str, Any]) -> str:
        """Создание предложения с учетом конфликтов с текущей истиной."""
        active_decisions = self.semantic.list_active_conflicts(target)
        confidence = self._calculate_confidence(stats['errors'], stats['successes'])
        
        proposal_ctx = ProposalContent(
            title=f"Address patterns in {target}",
            target=target,
            status=ProposalStatus.DRAFT,
            rationale=f"Observed {stats['errors']} issues vs {stats['successes']} successes.",
            confidence=confidence,
            evidence_event_ids=stats['evidence'],
            suggested_supersedes=active_decisions, # Конфликт гипотезы и истины
            hit_count=stats['errors'],
            miss_count=stats['successes'],
            first_observed_at=datetime.now(), # Начинаем отсчет инертности
            last_observed_at=datetime.now()
        )

        event = MemoryEvent(
            source="reflection_engine",
            kind=KIND_PROPOSAL,
            content=f"New proposal for {target}",
            context=proposal_ctx
        )
        return self.semantic.save(event)
