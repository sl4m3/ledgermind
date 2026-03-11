import pytest
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import DecisionStream

@pytest.fixture
def memory(tmp_path):
    storage = str(tmp_path / "ranking_mem")
    return Memory(storage_path=storage)

class TestSearchRankingSystem:
    def test_ranking_correctness_and_metadata(self, memory):
        """Verify that search returns correct results and extracts epistemic fields."""
        # 1. Setup a decision with enriched fields
        ctx = DecisionStream(
            decision_id="rank-1",
            title="Asynchronous Memory Enrichment Protocol",
            target="core/enrichment",
            rationale="Detailed logic for async processing.",
            compressive_rationale="TL;DR: Use background workers for LLM.",
            status="active",
            keywords=["async", "worker"],
            strengths=["Performance", "Responsiveness"]
        )
        memory.process_event(source="system", kind="decision", content="Protocol details", context=ctx)

        # 2. Search using keywords
        results = memory.search_decisions("asynchronous enrichment worker", limit=5)
        
        assert len(results) > 0
        top = results[0]
        assert "Asynchronous" in top['title']
        # Verify epistemic field extraction (Phase 2 & 5)
        assert top.get('compressive_rationale') == "TL;DR: Use background workers for LLM."
        assert "Performance" in top.get('strengths', [])
        # Verify similarity_score exists (Phase 3)
        assert 'similarity_score' in top

    def test_normative_lifecycle_weighting(self, memory):
        """Verify that Canonical/Active documents rank higher than Emergent/Dormant."""
        # 1. Canonical but decaying (Old standard)
        memory.process_event(
            source="system", kind="decision", content="Legacy",
            context={
                "decision_id": "old-1", "target": "storage/legacy", "title": "Legacy Storage",
                "rationale": "Old way of doing things.",
                "phase": "canonical", "vitality": "decaying" # 1.5 * 0.5 = 0.75 multiplier
            }
        )
        # 2. Emergent and Active (New hotness)
        memory.process_event(
            source="system", kind="decision", content="Modern",
            context={
                "decision_id": "new-1", "target": "storage/modern", "title": "Modern Storage",
                "rationale": "New optimized approach.",
                "phase": "emergent", "vitality": "active" # 1.2 * 1.0 = 1.2 multiplier
            }
        )

        results = memory.search_decisions("storage", mode="balanced")
        assert len(results) >= 2
        # Modern should be first due to higher vitality multiplier
        assert "Modern" in results[0]['title']
