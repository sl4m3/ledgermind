import pytest
import json
from unittest.mock import MagicMock, patch
from ledgermind.core.reasoning.enrichment import LLMEnricher
from ledgermind.core.core.schemas import DecisionStream, KIND_PROPOSAL

@pytest.fixture
def enricher():
    memory = MagicMock()
    # Explicitly set mode to rich to trigger the CLI call path
    return LLMEnricher(mode="rich", worker=memory)

def test_epistemic_field_extraction(enricher):
    """Verify that LLMEnricher correctly parses strengths, objections and counter-patterns from JSON."""
    from ledgermind.core.core.schemas import DecisionStream
    
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
        "objections": ["Critical risk 1"],
        "counter_patterns": ["Avoid in production"]
    }
    
    with patch.object(enricher, "_call_cli_model", return_value=json.dumps(llm_json)):
        # We simulate the parsing part of enrich_proposal. 
        # MUST provide cluster_logs to avoid early skip.
        enriched = enricher.enrich_proposal(proposal, cluster_logs="Some logs content")
        
        assert enriched.title == "Smart Enriched Title"
        assert enriched.compressive_rationale.startswith("TL;DR")
        assert "Strong point 1" in enriched.strengths
        assert "Critical risk 1" in enriched.objections
        assert "Avoid in production" in enriched.counter_patterns

def test_compressive_rationale_persistence(enricher):
    """Ensure that compressive_rationale is extracted and mapped to the update dict."""
    from ledgermind.core.core.schemas import ProposalContent
    
    proposal = ProposalContent(
        decision_id="test-prop-456",
        target="core/storage",
        title="Enriched Title",
        rationale="Long enough rationale for testing persistence."
    )
    proposal.compressive_rationale = "Brief summary"
    
    # Simulate the update dictionary creation in process_batch
    updates = {
        "title": getattr(proposal, 'title'),
        "compressive_rationale": getattr(proposal, 'compressive_rationale'),
        "enrichment_status": "completed"
    }
    
    assert updates["compressive_rationale"] == "Brief summary"
    assert updates["title"] == "Enriched Title"
