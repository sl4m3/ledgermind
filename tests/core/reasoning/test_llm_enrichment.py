import pytest
from unittest.mock import patch, MagicMock
from ledgermind.core.core.schemas import ProposalContent, ProceduralContent, ProceduralStep
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher

@pytest.fixture
def mock_proposal():
    return ProposalContent(
        title="Test Proposal",
        target="test_target",
        rationale="Distilled from multi-turn successful trajectory (ending at ID 42)",
        keywords=["test"],
        confidence=0.85,
        procedural=ProceduralContent(
            steps=[
                ProceduralStep(action="[PROMPT] Build a login form", rationale="User initiative: Build a login form"),
                ProceduralStep(action="[CALL] create_file('login.py')", rationale="Action: call"),
                ProceduralStep(action="[RESULT] File created", rationale="System outcome or decision state")
            ],
            target_task="test_target",
            success_evidence_ids=[40, 41, 42]
        )
    )

def test_enricher_lite_mode(mock_proposal):
    enricher = LLMEnricher(mode="lite")
    enriched = enricher.enrich_proposal(mock_proposal)
    assert enriched.rationale == "Distilled from multi-turn successful trajectory (ending at ID 42)"

@patch('httpx.Client.post')
def test_enricher_optimal_mode(mock_post, mock_proposal):
    enricher = LLMEnricher(mode="optimal")
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Enriched Local Summary"}}]
    }
    mock_post.return_value = mock_response

    enriched = enricher.enrich_proposal(mock_proposal)
    assert "Enriched Local Summary" in enriched.rationale
    assert "Original Data:" in enriched.rationale

@patch('httpx.Client.post')
def test_enricher_rich_mode(mock_post, mock_proposal, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    enricher = LLMEnricher(mode="rich")
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Enriched Cloud Summary"}}]
    }
    mock_post.return_value = mock_response

    enriched = enricher.enrich_proposal(mock_proposal)
    assert "Enriched Cloud Summary" in enriched.rationale
    assert "Original Data:" in enriched.rationale
    
def test_enricher_rich_mode_no_key(mock_proposal, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    enricher = LLMEnricher(mode="rich")
    
    enriched = enricher.enrich_proposal(mock_proposal)
    # Should fallback gracefully without modifying
    assert enriched.rationale == "Distilled from multi-turn successful trajectory (ending at ID 42)"
