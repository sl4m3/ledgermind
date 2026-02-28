import pytest
import os
import json
import subprocess
from unittest.mock import patch, MagicMock
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import ProposalContent, ProceduralContent, ProceduralStep, KIND_PROPOSAL
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher

@pytest.fixture
def test_memory(tmp_path):
    storage = tmp_path / "memory"
    return Memory(storage_path=str(storage))

@pytest.fixture
def sample_proposal():
    return ProposalContent(
        title="Raw Trajectory",
        target="network",
        rationale="Raw rationale",
        keywords=["net"],
        confidence=0.8,
        enrichment_status="pending",
        procedural=ProceduralContent(
            steps=[
                ProceduralStep(action="[PROMPT] setup firewall", rationale="User request"),
                ProceduralStep(action="[CALL] ufw allow 80", rationale="Action taken")
            ],
            target_task="network",
            success_evidence_ids=[1, 2]
        )
    )

# --- 1. Testing Modes ---

def test_mode_lite_does_nothing(sample_proposal):
    enricher = LLMEnricher(mode="lite")
    # Set to non-pending just in case
    sample_proposal.enrichment_status = "none"
    with patch('httpx.Client.post') as mock_post:
        enriched = enricher.enrich_proposal(sample_proposal)
        assert enriched.rationale == "Raw rationale"
        assert mock_post.call_count == 0

@patch('httpx.Client.post')
def test_mode_optimal_calls_local_api(mock_post, sample_proposal):
    enricher = LLMEnricher(mode="optimal")
    
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "Human Local Text"}}]}
    mock_post.return_value = mock_resp

    enriched = enricher.enrich_proposal(sample_proposal)
    assert "Human Local Text" in enriched.rationale
    assert "Raw rationale" in enriched.rationale # Original preserved in footer
    
    # Verify default URL
    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:11434/v1/chat/completions"

# --- 2. Testing CLI Integration (Rich Mode) ---

@patch('subprocess.run')
def test_rich_mode_prefers_gemini_cli(mock_run, sample_proposal):
    enricher = LLMEnricher(mode="rich", client_name="gemini")
    
    # Mock successful gemini run
    mock_run.return_value = MagicMock(stdout="Human Gemini Text", returncode=0)

    enriched = enricher.enrich_proposal(sample_proposal)
    assert "Human Gemini Text" in enriched.rationale
    
    # Verify CLI args
    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert "gemini" in cmd
    assert "--prompt" in cmd
    assert "setup firewall" in cmd[2] # Prompt should be there

@patch('subprocess.run')
@patch('httpx.Client.post')
def test_rich_mode_fallback_to_api_on_cli_failure(mock_post, mock_run, sample_proposal, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    enricher = LLMEnricher(mode="rich", client_name="gemini")
    
    # 1. CLI fails
    mock_run.side_effect = subprocess.CalledProcessError(127, "gemini")
    
    # 2. API succeeds
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "Human API Text"}}]}
    mock_post.return_value = mock_resp

    enriched = enricher.enrich_proposal(sample_proposal)
    assert "Human API Text" in enriched.rationale
    assert mock_post.called

# --- 3. Testing Batch Processing ---

def test_process_batch_filters_and_updates(test_memory, sample_proposal):
    # Mock vector to avoid indexing warnings
    test_memory.vector = MagicMock()
    
    # 1. Create a pending proposal
    # Ensure status is set
    sample_proposal.enrichment_status = "pending"
    res = test_memory.process_event(
        source="agent", kind=KIND_PROPOSAL, content=sample_proposal.title, context=sample_proposal
    )
    fid_pending = res.metadata["file_id"]
    
    # 2. Create a completed proposal
    completed_prop = sample_proposal.model_copy(deep=True)
    completed_prop.enrichment_status = "completed"
    res_done = test_memory.process_event(
        source="agent", kind=KIND_PROPOSAL, content="Already Done", context=completed_prop
    )
    fid_done = res_done.metadata["file_id"]
    
    # Run batch enrichment in 'optimal' mode (mocked)
    enricher = LLMEnricher(mode="optimal")
    with patch.object(enricher, '_call_model', return_value="Enriched!"):
        enricher.process_batch(test_memory)

    # Sync meta to ensure we read fresh data from DB
    test_memory.semantic.sync_meta_index()

    # Verify pending is updated
    meta_pending = test_memory.semantic.meta.get_by_fid(fid_pending)
    ctx_pending = json.loads(meta_pending['context_json'])
    assert ctx_pending['enrichment_status'] == "completed"
    
    # Verify rationale updated in file
    from ledgermind.core.stores.semantic_store.loader import MemoryLoader
    file_path = os.path.join(test_memory.semantic.repo_path, fid_pending)
    with open(file_path, 'r') as f:
        data, body = MemoryLoader.parse(f.read())
    assert "Enriched!" in data['context']['rationale']

def test_process_batch_handles_errors_gracefully(test_memory, sample_proposal):
    test_memory.vector = MagicMock()
    
    sample_proposal.enrichment_status = "pending"
    res = test_memory.process_event(
        source="agent", kind=KIND_PROPOSAL, content=sample_proposal.title, context=sample_proposal
    )
    fid = res.metadata["file_id"]
    
    enricher = LLMEnricher(mode="optimal")
    # Simulate LLM crash
    with patch.object(enricher, '_call_model', side_effect=RuntimeError("LLM Down")):
        enricher.process_batch(test_memory)
    
    # Sync and verify status remained 'pending'
    test_memory.semantic.sync_meta_index()
    meta = test_memory.semantic.meta.get_by_fid(fid)
    ctx = json.loads(meta['context_json'])
    assert ctx['enrichment_status'] == "pending"
