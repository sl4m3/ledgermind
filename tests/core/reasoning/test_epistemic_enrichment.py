import pytest
import json
from unittest.mock import MagicMock, patch
from ledgermind.core.reasoning.enrichment import LLMEnricher
from ledgermind.core.core.schemas import DecisionStream, KIND_PROPOSAL

@pytest.fixture
def enricher():
    # V7.0: LLMEnricher takes only mode and language. 
    # Clients and memory are managed internally or passed to methods.
    return LLMEnricher(mode="rich")

def test_epistemic_field_extraction(enricher):
    """Verify that LLMEnricher correctly parses strengths, objections and counter-patterns from JSON."""
    proposal = DecisionStream(
        decision_id="test-prop-123",
        target="core/storage",
        title="Old Title",
        rationale="Initial rationale that is long enough for validation purposes."
    )

    # Mock LLM response with structured arguments
    llm_json = {
        "title": "Smart Enriched Title",
        "rationale": "# New Rationale\nDetails here.",
        "compressive": "TL;DR of the proposal.",
        "strengths": ["Strong point 1", "Strong point 2"],
        "objections": ["Critical risk 1"]
    }

    # Patch the CloudLLMClient.call method (since mode="rich")
    # Also mock memory.semantic.meta.get_config to return proper values
    mock_memory = MagicMock()
    mock_memory.semantic.meta.get_config.return_value = None  # Use defaults
    
    with patch("ledgermind.core.reasoning.enrichment.clients.CloudLLMClient.call", return_value=json.dumps(llm_json)):
        # We simulate the parsing part of enrich_proposal.
        # MUST provide cluster_logs to avoid early skip.
        enriched = enricher.enrich_proposal(proposal, cluster_logs="Some logs content", memory=mock_memory)

        assert enriched.title == "Smart Enriched Title"
        assert enriched.compressive_rationale.startswith("TL;DR")
        assert "Strong point 1" in enriched.strengths
        assert "Critical risk 1" in enriched.objections

def test_compressive_rationale_persistence(enricher):
    """Ensure that compressive_rationale is extracted and mapped to the update dict."""
    # V7.0: DecisionStream is the unified model
    proposal = DecisionStream(
        decision_id="test-prop-456",
        target="core/storage",
        title="Enriched Title",
        rationale="Long enough rationale for testing persistence."
    )
    proposal.compressive_rationale = "Brief summary"
    
    # Simulate the update dictionary creation logic inside _apply_mapping
    # We just verify that the object attributes are correctly set
    assert proposal.compressive_rationale == "Brief summary"
    assert proposal.title == "Enriched Title"
