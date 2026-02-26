import pytest
import os
from typing import List
from ledgermind.core.reasoning.resolution import ResolutionEngine
from ledgermind.core.core.schemas import ResolutionIntent

class TestResolutionEngine:

    @pytest.fixture
    def engine(self, tmp_path):
        store_path = tmp_path / "test_store"
        # ResolutionEngine just takes a path string, doesn't need to exist for validate_intent
        return ResolutionEngine(semantic_store_path=str(store_path))

    def test_validate_intent_abort(self, engine):
        """Test that validate_intent returns False if resolution_type is 'abort'."""
        intent = ResolutionIntent(
            resolution_type="abort",
            rationale="Aborting because reasons exist.",
            target_decision_ids=["conflict_1"]
        )
        conflict_files = ["conflict_1"]
        assert engine.validate_intent(intent, conflict_files) is False

    def test_validate_intent_valid_subset(self, engine):
        """Test that validate_intent returns True if conflict_files is a subset of target_decision_ids."""
        intent = ResolutionIntent(
            resolution_type="supersede",
            rationale="Superseding due to reasons.",
            target_decision_ids=["conflict_1", "conflict_2"]
        )
        conflict_files = ["conflict_1"]
        assert engine.validate_intent(intent, conflict_files) is True

    def test_validate_intent_exact_match(self, engine):
        """Test that validate_intent returns True if conflict_files matches target_decision_ids exactly."""
        intent = ResolutionIntent(
            resolution_type="deprecate",
            rationale="Deprecating due to obsolescence.",
            target_decision_ids=["conflict_1"]
        )
        conflict_files = ["conflict_1"]
        assert engine.validate_intent(intent, conflict_files) is True

    def test_validate_intent_missing_conflict(self, engine):
        """Test that validate_intent returns False if a conflict file is not covered by the intent."""
        intent = ResolutionIntent(
            resolution_type="supersede",
            rationale="Superseding partial set.",
            target_decision_ids=["conflict_1"]
        )
        conflict_files = ["conflict_1", "conflict_2"]
        assert engine.validate_intent(intent, conflict_files) is False

    def test_validate_intent_empty_conflicts(self, engine):
        """Test that validate_intent returns True if there are no conflict files."""
        intent = ResolutionIntent(
            resolution_type="supersede",
            rationale="Superseding anyway.",
            target_decision_ids=["conflict_1"]
        )
        conflict_files = []
        assert engine.validate_intent(intent, conflict_files) is True

    def test_validate_intent_empty_both(self, engine):
        """Test that validate_intent returns True if both lists are empty (vacuously true)."""
        intent = ResolutionIntent(
            resolution_type="supersede",
            rationale="Superseding nothing.",
            target_decision_ids=[]
        )
        conflict_files = []
        assert engine.validate_intent(intent, conflict_files) is True
