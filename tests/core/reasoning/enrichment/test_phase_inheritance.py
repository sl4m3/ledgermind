"""
Tests for phase inheritance during consolidation.
"""
import pytest
from ledgermind.core.reasoning.enrichment.facade import LLMEnricher
from ledgermind.core.core.schemas import DecisionPhase


class TestPhaseInheritance:
    """Test LLMEnricher._inherit_phase_with_validation()."""

    @pytest.fixture
    def enricher(self):
        return LLMEnricher()

    def test_inherit_phase_pattern_only(self, enricher):
        """PATTERN + PATTERN → PATTERN."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[DecisionPhase.PATTERN, DecisionPhase.PATTERN],
            total_evidence_count=2,
            stability_score=0.3
        )
        assert result == DecisionPhase.PATTERN

    def test_inherit_phase_emergent_with_enough_evidence(self, enricher):
        """PATTERN + EMERGENT (evidence≥5, stability≥0.5) → EMERGENT."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[DecisionPhase.PATTERN, DecisionPhase.EMERGENT],
            total_evidence_count=10,
            stability_score=0.6
        )
        assert result == DecisionPhase.EMERGENT

    def test_inherit_phase_emergent_with_low_evidence(self, enricher):
        """PATTERN + EMERGENT (evidence<5) → PATTERN (понижено)."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[DecisionPhase.PATTERN, DecisionPhase.EMERGENT],
            total_evidence_count=3,  # < 5
            stability_score=0.6
        )
        assert result == DecisionPhase.PATTERN

    def test_inherit_phase_emergent_with_low_stability(self, enricher):
        """PATTERN + EMERGENT (stability<0.5) → PATTERN (понижено)."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[DecisionPhase.PATTERN, DecisionPhase.EMERGENT],
            total_evidence_count=10,
            stability_score=0.3  # < 0.5
        )
        assert result == DecisionPhase.PATTERN

    def test_inherit_phase_canonical_with_enough_metrics(self, enricher):
        """EMERGENT + CANONICAL (evidence≥15, stability≥0.7) → CANONICAL."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[DecisionPhase.EMERGENT, DecisionPhase.CANONICAL],
            total_evidence_count=20,
            stability_score=0.8
        )
        assert result == DecisionPhase.CANONICAL

    def test_inherit_phase_canonical_with_low_evidence(self, enricher):
        """EMERGENT + CANONICAL (evidence<15) → EMERGENT (понижено)."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[DecisionPhase.EMERGENT, DecisionPhase.CANONICAL],
            total_evidence_count=10,  # < 15
            stability_score=0.8
        )
        assert result == DecisionPhase.EMERGENT

    def test_inherit_phase_canonical_with_low_stability(self, enricher):
        """EMERGENT + CANONICAL (stability<0.7) → EMERGENT (понижено)."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[DecisionPhase.EMERGENT, DecisionPhase.CANONICAL],
            total_evidence_count=20,
            stability_score=0.5  # < 0.7
        )
        assert result == DecisionPhase.EMERGENT

    def test_inherit_phase_empty_source(self, enricher):
        """Пустой список → PATTERN (default)."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[],
            total_evidence_count=0,
            stability_score=0.0
        )
        assert result == DecisionPhase.PATTERN

    def test_inherit_phase_mixed_all_three(self, enricher):
        """PATTERN + EMERGENT + CANONICAL с достаточными метриками → CANONICAL."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[DecisionPhase.PATTERN, DecisionPhase.EMERGENT, DecisionPhase.CANONICAL],
            total_evidence_count=25,
            stability_score=0.75
        )
        assert result == DecisionPhase.CANONICAL

    def test_inherit_phase_mixed_all_three_low_metrics(self, enricher):
        """PATTERN + EMERGENT + CANONICAL с низкими метриками → PATTERN."""
        result = enricher._inherit_phase_with_validation(
            source_phases=[DecisionPhase.PATTERN, DecisionPhase.EMERGENT, DecisionPhase.CANONICAL],
            total_evidence_count=3,  # < 5
            stability_score=0.3  # < 0.5
        )
        assert result == DecisionPhase.PATTERN
