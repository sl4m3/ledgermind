import pytest
import os
import json
from unittest.mock import patch, MagicMock
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import ProposalContent, KIND_PROPOSAL
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher

@pytest.fixture
def test_memory(tmp_path):
    storage = tmp_path / "memory"
    os.makedirs(storage / "semantic")
    # Mock VectorStore
    with patch('ledgermind.core.api.memory.VectorStore'):
        mem = Memory(str(storage))
        # Also mock episodic storage
        mem.episodic = MagicMock()
        mem.episodic.get_batch_by_ids.return_value = [
            {"timestamp": "2026-03-08", "kind": "result", "content": "Log 1"},
            {"timestamp": "2026-03-08", "kind": "call", "content": "Log 2"}
        ]
        yield mem

@pytest.fixture
def sample_proposal():
    return ProposalContent(
        decision_id="test-1",
        title="Raw Trajectory",
        target="network",
        rationale="Observed execution trajectory for network setup. Needs synthesis.",
        keywords=["net", "firewall"],
        confidence=0.8,
        enrichment_status="pending",
        evidence_event_ids=[1, 2, 3]
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
    
    # Patch the internal local model caller
    with patch.object(enricher, "_call_local_model", return_value=json.dumps(valid_json)):
        result = enricher.enrich_proposal(sample_proposal, cluster_logs="some logs")
        assert result.enrichment_status == "completed"
        assert result.title == "Enhanced Network"
        assert result.compressive_rationale == "TL;DR"

def test_rich_mode_calls_cloud_model(sample_proposal):
    """Verify that rich mode triggers cloud model paths."""
    enricher = LLMEnricher(mode="rich")
    
    valid_json = {
        "title": "Rich Title",
        "rationale": "Rich rationale.",
        "compressive": "Rich TL;DR"
    }
    
    # Patch the high-level cloud caller
    with patch.object(enricher, "_call_cloud_model", return_value=json.dumps(valid_json)):
        result = enricher.enrich_proposal(sample_proposal, cluster_logs="some logs")
        assert result.enrichment_status == "completed"
        assert result.title == "Rich Title"

def test_process_batch_integration(test_memory, sample_proposal):
    """Check batch processing across multiple proposals."""
    enricher = LLMEnricher(mode="optimal")
    valid_json = {"title": "Batch Result", "rationale": "Rationale."}
    
    with patch.object(enricher, "_call_local_model", return_value=json.dumps(valid_json)):
        results = enricher.process_batch([sample_proposal], test_memory.episodic)
        assert len(results) == 1
        assert results[0].enrichment_status == "completed"
        assert results[0].title == "Batch Result"

def test_process_batch_handles_errors(test_memory, sample_proposal):
    """Verify system resilience when LLM returns garbage or fails."""
    enricher = LLMEnricher(mode="optimal")
    
    # LLM fails (returns None)
    with patch.object(enricher, "_call_local_model", return_value=None):
        results = enricher.process_batch([sample_proposal], test_memory.episodic)
        assert len(results) == 1
        # Should return original proposal unchanged (pending)
        assert results[0].enrichment_status == "pending"
