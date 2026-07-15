import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.knowledge import KnowledgeItem, Phase
from ledgermind.core.reasoning.metrics import (
    calculate_confidence,
    calculate_stability,
    calculate_utility,
    calculate_coverage,
    count_evidence,
)

def test_confidence_calculation():
    assert calculate_confidence(0) == 0.0
    assert calculate_confidence(1) == pytest.approx(0.30, abs=0.01)
    assert calculate_confidence(10) == 1.0
    assert calculate_confidence(100) == 1.0

def test_coverage_calculation():
    first_seen = datetime.now() - timedelta(days=15)
    last_seen = datetime.now()
    assert calculate_coverage(first_seen, last_seen) == pytest.approx(0.5, abs=0.01)

def test_utility_calculation():
    utility = calculate_utility(
        stability_score=0.5,
        confidence=0.7,
        coverage=0.5,
    )
    assert utility == pytest.approx(0.5 * 0.3 + 0.7 * 0.5 + 0.5 * 0.2, abs=0.01)

def test_count_evidence():
    # Mock knowledge items
    item_a = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="p", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        supersedes=["pattern_B_def", "pattern_C_ghi"],
    )
    item_b = KnowledgeItem(
        fid="pattern_B_def", title="B", target="t", profile="p", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        supersedes=[],
    )
    item_c = KnowledgeItem(
        fid="pattern_C_ghi", title="C", target="t", profile="p", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        supersedes=[],
    )
    items = {
        "pattern_A_abc": item_a,
        "pattern_B_def": item_b,
        "pattern_C_ghi": item_c,
    }
    assert count_evidence("pattern_A_abc", items) == 2
