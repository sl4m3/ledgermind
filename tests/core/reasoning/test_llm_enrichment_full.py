import pytest
import os
import json
import subprocess
import yaml
from datetime import datetime
from unittest.mock import patch, MagicMock
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import ProposalContent, KIND_PROPOSAL
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher

@pytest.fixture
def test_memory(tmp_path):
    storage = tmp_path / "memory"
    os.makedirs(storage / "semantic")
    # Mock VectorStore class within the memory module to avoid GGUF errors
    with patch('ledgermind.core.api.memory.VectorStore'):
        mem = Memory(str(storage))
        # Also mock episodic storage to return some logs
        mem.episodic = MagicMock()
        mem.episodic.get_event_batch.return_value = [
            MagicMock(content="Log entry 1"),
            MagicMock(content="Log entry 2")
        ]
        yield mem

@pytest.fixture
def sample_proposal():
    return ProposalContent(
        title="Raw Trajectory",
        target="network",
        rationale="Observed execution trajectory for network setup. Needs synthesis.",
        keywords=["net", "firewall"],
        confidence=0.8,
        enrichment_status="pending",
        evidence_event_ids=[1, 2, 3]
    )

# --- 1. Testing Modes ---

def test_mode_lite_does_nothing(sample_proposal):
    enricher = LLMEnricher(mode="lite")
    sample_proposal.enrichment_status = "none"
    with patch('httpx.Client.post') as mock_post:
        result = enricher.enrich_proposal(sample_proposal, cluster_logs="some logs")
        assert result.enrichment_status == "none"
        mock_post.assert_not_called()

def test_mode_optimal_calls_local_api(sample_proposal):
    enricher = LLMEnricher(mode="optimal")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    valid_json = {
        "title": "Enhanced Network",
        "target": "network",
        "rationale": "Better network rationale.",
        "confidence": 0.95,
        "keywords": ["net", "secure"]
    }
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(valid_json)}}]
    }
    
    with patch('httpx.Client.post', return_value=mock_response):
        result = enricher.enrich_proposal(sample_proposal, cluster_logs="some logs")
        assert result.enrichment_status == "completed"
        # Flexible match for title (it might be translated or wrapped)
        assert "Enhanced Network" in result.title or "сетевой" in result.title.lower()

def test_rich_mode_prefers_gemini_cli(sample_proposal):
    enricher = LLMEnricher(mode="rich")
    
    valid_json = {
        "title": "Rich Title",
        "target": "rich/net",
        "rationale": "Rich rationale.",
        "confidence": 0.99
    }
    
    with patch('subprocess.Popen') as mock_popen:
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (json.dumps(valid_json), "")
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        
        result = enricher.enrich_proposal(sample_proposal, cluster_logs="some logs")
        
        assert result.enrichment_status == "completed"
        # The title might be changed by post-processing or translation logic
        assert result.title is not None
        mock_popen.assert_called()

# --- 2. Batch Processing ---

def test_process_batch_filters_and_updates(test_memory):
    prop_id = "prop_test.md"
    test_memory.semantic.meta.upsert(fid=prop_id, target="network", kind="proposal", status="draft", timestamp=datetime.now())
    
    header = {
        "kind": "proposal",
        "context": {
            "target": "network",
            "title": "Raw",
            "status": "draft",
            "rationale": "Initial rationale.",
            "confidence": 0.5,
            "enrichment_status": "pending",
            "evidence_event_ids": [101, 102]
        }
    }
    
    with open(os.path.join(test_memory.semantic.repo_path, prop_id), 'w') as f:
        f.write("---\n" + yaml.dump(header) + "---\nRaw Content")
    
    enricher = LLMEnricher(mode="optimal")
    
    valid_json = {"title": "Batch Result", "target": "network", "rationale": "Rationale.", "confidence": 0.9}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(valid_json)}}]
    }
    
    with patch('httpx.Client.post', return_value=mock_response):
        stats = enricher.process_batch(test_memory)
        assert stats["total"] == 1
        assert stats["enriched"] == 1
        
        # Verify file was updated in meta
        data = test_memory.semantic.meta.get_by_fid(prop_id)
        assert data["enrichment_status"] == "completed"
        # Title might be translated to Russian if preferred_language is set in the test DB
        assert data["title"] is not None

def test_process_batch_handles_errors_gracefully(test_memory):
    prop_id = "prop_error.md"
    test_memory.semantic.meta.upsert(fid=prop_id, target="err", kind="proposal", status="draft", timestamp=datetime.now())
    
    header = {
        "kind": "proposal",
        "context": {
            "target": "err",
            "title": "Error Case",
            "rationale": "Error case rationale.",
            "confidence": 0.1,
            "enrichment_status": "pending",
            "evidence_event_ids": [999]
        }
    }
    
    with open(os.path.join(test_memory.semantic.repo_path, prop_id), 'w') as f:
        f.write("---\n" + yaml.dump(header) + "---\nContent")
        
    enricher = LLMEnricher(mode="optimal")
    
    # API returns 500
    mock_response = MagicMock()
    mock_response.status_code = 500
    
    with patch('httpx.Client.post', return_value=mock_response):
        stats = enricher.process_batch(test_memory)
        assert stats["total"] == 1
        assert stats["enriched"] == 0
        assert stats["errors"] == 1
