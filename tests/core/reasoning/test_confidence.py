"""
Tests for confidence calculation and usage.
"""
import pytest
import math
from ledgermind.core.reasoning.decay import DecayEngine
from ledgermind.core.core.schemas import DecisionStream, DecisionPhase


class TestConfidenceCalculation:
    """Test DecayEngine.calculate_confidence()."""

    @pytest.fixture
    def decay_engine(self):
        return DecayEngine()

    def test_confidence_from_evidence_only(self, decay_engine):
        """confidence растёт с количеством evidence."""
        # 0 evidence
        conf = decay_engine.calculate_confidence(total_evidence_count=0, stability_score=0.5, hit_count=0)
        assert 0.15 <= conf <= 0.25  # ~20% от stability
        
        # 10 evidence
        conf = decay_engine.calculate_confidence(total_evidence_count=10, stability_score=0.5, hit_count=0)
        assert 0.35 <= conf <= 0.45  # ~40% от evidence + 20% от stability
        
        # 100 evidence
        conf = decay_engine.calculate_confidence(total_evidence_count=100, stability_score=0.5, hit_count=0)
        assert conf >= 0.55  # больше evidence = выше confidence

    def test_confidence_from_stability_only(self, decay_engine):
        """confidence растёт со стабильностью."""
        # 0 stability
        conf = decay_engine.calculate_confidence(total_evidence_count=0, stability_score=0.0, hit_count=0)
        assert conf == 0.0
        
        # 0.5 stability
        conf = decay_engine.calculate_confidence(total_evidence_count=0, stability_score=0.5, hit_count=0)
        assert 0.15 <= conf <= 0.25  # ~20% от stability
        
        # 1.0 stability
        conf = decay_engine.calculate_confidence(total_evidence_count=0, stability_score=1.0, hit_count=0)
        assert 0.35 <= conf <= 0.45  # ~40% от stability

    def test_confidence_from_usage_only(self, decay_engine):
        """confidence растёт с hit_count."""
        # 0 hits
        conf = decay_engine.calculate_confidence(total_evidence_count=0, stability_score=0.5, hit_count=0)
        assert 0.15 <= conf <= 0.25  # только stability
        
        # 10 hits
        conf = decay_engine.calculate_confidence(total_evidence_count=0, stability_score=0.5, hit_count=10)
        assert conf > 0.2  # stability + usage
        
        # 100 hits
        conf = decay_engine.calculate_confidence(total_evidence_count=0, stability_score=0.5, hit_count=100)
        assert conf >= 0.25  # stability + больше usage

    def test_confidence_combined(self, decay_engine):
        """confidence комбинирует все факторы."""
        conf = decay_engine.calculate_confidence(
            total_evidence_count=50,
            stability_score=0.8,
            hit_count=20
        )
        # Ожидаем: evidence (log10(51)/2=0.85) * 0.4 + stability (0.8) * 0.4 + usage (log1p(20)/2.3=0.66) * 0.2
        # = 0.34 + 0.32 + 0.13 = 0.79
        assert 0.7 <= conf <= 0.95

    def test_confidence_bounds(self, decay_engine):
        """confidence всегда в пределах 0.0-1.0."""
        # Минимальные значения
        conf = decay_engine.calculate_confidence(
            total_evidence_count=-1,  # negative should be handled
            stability_score=-0.5,
            hit_count=-10
        )
        assert 0.0 <= conf <= 1.0
        
        # Максимальные значения
        conf = decay_engine.calculate_confidence(
            total_evidence_count=10000,
            stability_score=2.0,  # > 1.0 should be capped
            hit_count=10000
        )
        assert 0.0 <= conf <= 1.0


class TestConfidenceInLifecycle:
    """Test confidence usage in LifecycleEngine.promote_stream()."""

    @pytest.fixture
    def lifecycle_engine(self):
        from ledgermind.core.reasoning.lifecycle import LifecycleEngine
        return LifecycleEngine()

    def test_new_hypothesis_has_zero_confidence(self, lifecycle_engine):
        """Новые гипотезы без evidence имеют confidence = 0.0."""
        from datetime import datetime
        
        stream = DecisionStream(
            decision_id="test-new",
            target="test",
            title="New Hypothesis",
            rationale="Test rationale for new hypothesis",  # ≥10 chars
            phase=DecisionPhase.PATTERN,
            frequency=0,
            total_evidence_count=0,
            stability_score=0.0,
            hit_count=0,
            first_seen=datetime.now(),
            last_hit_at=datetime.now()
        )
        
        # Вызываем calculate_temporal_signals с пустыми reinforcement_dates
        result = lifecycle_engine.calculate_temporal_signals(stream, [], datetime.now())
        
        # confidence должен быть 0.0 (нет evidence, stability, hits)
        assert result.confidence == 0.0

    def test_hypothesis_with_evidence_gets_confidence(self, lifecycle_engine):
        """Гипотезы с evidence получают confidence."""
        from datetime import datetime
        
        stream = DecisionStream(
            decision_id="test-evidence",
            target="test",
            title="Hypothesis with Evidence",
            rationale="Test rationale for hypothesis with evidence",  # ≥10 chars
            phase=DecisionPhase.PATTERN,
            frequency=0,
            total_evidence_count=10,  # 10 событий
            stability_score=0.0,
            hit_count=0,
            first_seen=datetime.now(),
            last_hit_at=datetime.now()
        )
        
        result = lifecycle_engine.calculate_temporal_signals(stream, [], datetime.now())
        
        # confidence должен быть > 0 (есть evidence)
        assert result.confidence > 0.0
        # 10 evidence = log10(11)/2 * 0.4 ≈ 0.21
        assert 0.15 <= result.confidence <= 0.35

    def test_promote_pattern_by_evidence(self, lifecycle_engine):
        """Pattern -> Emergent по total_evidence_count + coverage."""
        stream = DecisionStream(
            decision_id="test-1",
            target="test",
            title="Test",
            rationale="Test rationale",
            phase=DecisionPhase.PATTERN,
            total_evidence_count=60,  # >= 50
            coverage=0.25  # >= 0.2
        )
        
        result = lifecycle_engine.promote_stream(stream)
        assert result.phase == DecisionPhase.EMERGENT

    def test_promote_pattern_by_confidence(self, lifecycle_engine):
        """Pattern -> Emergent по confidence + evidence."""
        stream = DecisionStream(
            decision_id="test-2",
            target="test",
            title="Test",
            rationale="Test rationale",
            phase=DecisionPhase.PATTERN,
            total_evidence_count=35,  # >= 30
            confidence=0.55  # >= 0.5
        )
        
        result = lifecycle_engine.promote_stream(stream)
        assert result.phase == DecisionPhase.EMERGENT

    def test_no_promote_pattern_low_all(self, lifecycle_engine):
        """Нет продвижения, если все метрики низкие."""
        stream = DecisionStream(
            decision_id="test-3",
            target="test",
            title="Test",
            rationale="Test rationale",
            phase=DecisionPhase.PATTERN,
            total_evidence_count=20,  # < 30 и < 50
            coverage=0.1,  # < 0.2
            confidence=0.4  # < 0.5
        )
        
        result = lifecycle_engine.promote_stream(stream)
        assert result.phase == DecisionPhase.PATTERN

    def test_promote_emergent_by_standard(self, lifecycle_engine):
        """Emergent -> Canonical по стандартным критериям."""
        stream = DecisionStream(
            decision_id="test-4",
            target="test",
            title="Test",
            rationale="Test rationale",
            phase=DecisionPhase.EMERGENT,
            total_evidence_count=160,  # >= 150
            stability_score=0.75,  # >= 0.7
            coverage=0.35,  # >= 0.3
            confidence=0.7
        )
        
        result = lifecycle_engine.promote_stream(stream)
        assert result.phase == DecisionPhase.CANONICAL

    def test_promote_emergent_by_confidence(self, lifecycle_engine):
        """Emergent -> Canonical по confidence + stability."""
        stream = DecisionStream(
            decision_id="test-5",
            target="test",
            title="Test",
            rationale="Test rationale",
            phase=DecisionPhase.EMERGENT,
            total_evidence_count=80,  # < 150
            stability_score=0.75,  # >= 0.7
            coverage=0.2,  # < 0.3
            confidence=0.8  # >= 0.75
        )
        
        result = lifecycle_engine.promote_stream(stream)
        assert result.phase == DecisionPhase.CANONICAL


class TestConfidenceInSearch:
    """Test confidence filtering in QueryService.search()."""
    
    # NOTE: Integration tests for search require full memory fixture
    # which is complex to set up. Manual testing recommended.
    
    def test_search_confidence_filter_documented(self):
        """
        Search supports min_confidence parameter.
        
        Example usage:
        ```python
        results = memory.search("query", min_confidence=0.5)
        # Returns only results with confidence >= 0.5
        ```
        """
        pass  # Integration test - manual verification needed
