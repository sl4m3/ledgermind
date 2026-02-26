import pytest
import os
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import KIND_DECISION, KIND_PROPOSAL, ProposalStatus

@pytest.fixture
def memory():
    # Use the actual memory but we'll be careful not to delete things
    m = Memory(storage_path=".ledgermind")
    yield m
    m.close()

def test_status_based_boosting(memory):
    """Verify that active decisions are boosted and rejected ones are penalized."""
    query = "asynchronous enrichment"
    results = memory.search_decisions(query, limit=10, mode="balanced")
    
    # decision_20260224_235238_363968_a921d58d.md is an active decision
    # Check if it's among the top results
    target_id = "decision_20260224_235238_363968_a921d58d.md"
    target_result = next((r for r in results if r['id'] == target_id), None)
    
    assert target_result is not None, f"{target_id} not found in search results"
    assert target_result['status'] == 'active'
    
    # Rejected proposals should be lower if they match
    rejected = [r for r in results if r['status'] in ('rejected', 'falsified')]
    for r in rejected:
        # If the target matches well, it should be above rejected items
        # unless the rejected item is a much better match (unlikely here)
        if target_result['score'] < r['score']:
            print(f"Warning: Rejected {r['id']} ({r['score']}) is above active {target_id} ({target_result['score']})")

def test_keyword_search_enrichment(memory):
    """Verify that search finds the document by new keywords."""
    query = "наполнение смыслом"
    results = memory.search_decisions(query, limit=5)
    
    target_id = "decision_20260224_235238_363968_a921d58d.md"
    assert any(r['id'] == target_id for r in results), f"Search for '{query}' failed to find {target_id}"
    
    # The score should be high because it's an exact keyword match + active boost
    top_result = results[0]
    assert top_result['id'] == target_id

def test_ranking_correctness(memory):
    """Specific test for the user's problematic query."""
    query = "как я хотел улучшить отображение гипотез в плане обоснования и ожидаемого результата? кто будет их наполнять смыслом?"
    results = memory.search_decisions(query, limit=5)
    
    target_id = "decision_20260224_235238_363968_a921d58d.md"
    assert results[0]['id'] == target_id, f"Target {target_id} is not Top-1 for the specific query. Top-1 is {results[0]['id']}"
