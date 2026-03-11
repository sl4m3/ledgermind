import json
import pytest
from unittest.mock import patch, MagicMock
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import DecisionStream
from ledgermind.core.reasoning.enrichment import LLMEnricher

@pytest.fixture
def test_memory(tmp_path):
    storage = str(tmp_path)
    memory = Memory(storage_path=storage)
    return memory

@pytest.fixture
def sample_proposal():
    return DecisionStream(
        decision_id="test-1",
        title="Raw Trajectory",
        target="network",
        status="draft",
        rationale="Observed execution trajectory for network subsystem."
    )

def test_mode_optimal_calls_local_llm(sample_proposal):
    """Verify that optimal mode uses the local model logic."""
    enricher = LLMEnricher(mode="optimal")

    valid_json = {
        "title": "Enhanced Network",
        "rationale": "Better network rationale.",
        "compressive": "TL;DR",
        "strengths": ["S1"]
    }

    # Patch the LocalLLMClient.call method
    with patch("ledgermind.core.reasoning.enrichment.clients.LocalLLMClient.call", return_value=json.dumps(valid_json)):
        # We need a mock for memory/episodic store
        mock_episodic = MagicMock()
        mock_episodic.get_by_ids.return_value = []
        
        res = enricher.enrich_proposal(sample_proposal, cluster_logs="logs", memory=MagicMock())
        assert res.title == "Enhanced Network"
        assert "S1" in res.strengths

def test_rich_mode_calls_cloud_model(sample_proposal):
    """Verify that rich mode triggers cloud model paths."""
    enricher = LLMEnricher(mode="rich")

    valid_json = {
        "title": "Rich Title",
        "rationale": "Rich rationale.",
        "compressive": "Rich TL;DR"
    }

    # Patch the CloudLLMClient.call method
    with patch("ledgermind.core.reasoning.enrichment.clients.CloudLLMClient.call", return_value=json.dumps(valid_json)):
        res = enricher.enrich_proposal(sample_proposal, cluster_logs="logs", memory=MagicMock())
        assert res.title == "Rich Title"
        assert res.compressive_rationale.startswith("Rich TL;DR")

def test_process_batch_integration(test_memory, sample_proposal):
    """Check batch processing across multiple proposals."""
    enricher = LLMEnricher(mode="optimal")
    valid_json = {"title": "Batch Result", "rationale": "Rationale."}

    # Save proposal to semantic store so it has a fid
    res = test_memory.record_decision(sample_proposal.title, sample_proposal.target, sample_proposal.rationale)
    fid = res.metadata.get("file_id")
    
    # Reload from disk to get a proper object with fid
    meta = test_memory.semantic.meta.get_by_fid(fid)
    
    # We need to simulate proposals with evidence_event_ids to trigger the loop
    test_memory.semantic.update_decision(fid, {"evidence_event_ids": [1, 2]}, "Mock evidence")
    
    # Create an object that looks like what run_auto_enrichment creates
    class MockProp:
        def __init__(self, fid, data):
            self.fid = fid
            self.title = data.get('title')
            self.target = data.get('target')
            ctx = json.loads(data.get('context_json', '{}'))
            self.rationale = ctx.get('rationale')
            self.evidence_event_ids = ctx.get('evidence_event_ids') or [1, 2]
            self.total_evidence_count = 0
        def model_dump(self, mode=None):
            return {"title": self.title, "rationale": self.rationale, "evidence_event_ids": self.evidence_event_ids}

    prop_obj = MockProp(fid, meta)

    with patch("ledgermind.core.reasoning.enrichment.clients.LocalLLMClient.call", return_value=json.dumps(valid_json)):
        # Mock LogProcessor to return something
        with patch("ledgermind.core.reasoning.enrichment.processor.LogProcessor.get_batch_logs", return_value=("logs", [1, 2], [])):
            results = enricher.process_batch([prop_obj], test_memory.episodic, memory=test_memory)
            assert len(results) == 1
            assert results[0].title == "Batch Result"
