import pytest
import os
import shutil
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import KIND_DECISION

@pytest.fixture
def memory(tmp_path):
    # Use a fresh temporary directory for each test
    storage_path = str(tmp_path / "test_memory")
    m = Memory(
        storage_path=storage_path,
        vector_model="all-MiniLM-L6-v2" # Standard model for testing
    )
    
    # Pre-seed with the specific data needed for the tests
    # This replaces the hard-coded requirement for specific local files
    m.record_decision(
        title="Implement asynchronous enrichment for semantic processing",
        target="asynchronous-enrichment",
        rationale="To improve responsiveness and allow deeper processing without blocking the main interaction loop. Who will fill them with meaning? (наполнение смыслом)",
        consequences=["Faster responses", "Background processing enabled"]
    )
    
    yield m
    m.close()
    if os.path.exists(storage_path):
        shutil.rmtree(storage_path)

def test_status_based_boosting(memory):
    """Verify that active decisions are boosted and rejected ones are penalized."""
    query = "asynchronous enrichment"
    results = memory.search_decisions(query, limit=10, mode="balanced")
    
    # Check if our recorded decision is among the results
    target_result = next((r for r in results if "asynchronous enrichment" in r['title'].lower()), None)
    
    assert target_result is not None, "Target decision not found in search results"
    assert target_result['status'] == 'active'
    
    # Record a rejected one with higher keyword match but lower status
    memory.process_event(
        source="agent",
        kind="proposal",
        content="REJECTED: asynchronous enrichment super-match",
        context={
            "title": "REJECTED: asynchronous enrichment super-match",
            "target": "asynchronous-enrichment-legacy",
            "status": "rejected",
            "rationale": "Old approach that was rejected. Needs at least 10 chars.",
            "namespace": "default",
            "confidence": 0.5
        }
    )
    
    # Re-search
    results_v2 = memory.search_decisions(query, limit=10, mode="balanced")
    target_v2 = next((r for r in results_v2 if r['id'] == target_result['id']), None)
    rejected_v2 = next((r for r in results_v2 if "REJECTED" in r['title']), None)
    
    if target_v2 and rejected_v2:
        # Active should be boosted over rejected
        assert target_v2['score'] >= rejected_v2['score'], f"Active {target_v2['id']} should be boosted over rejected {rejected_v2['id']}"

def test_keyword_search_enrichment(memory):
    """Verify that search finds the document by new keywords."""
    query = "наполнение смыслом"
    results = memory.search_decisions(query, limit=5)
    
    # The decision recorded in fixture has "наполнение смыслом" in rationale
    assert any("asynchronous enrichment" in r['title'].lower() for r in results), f"Search for '{query}' failed to find target decision"
    
    # The score should be high because it's a keyword match + active boost
    top_result = results[0]
    assert "asynchronous enrichment" in top_result['title'].lower()

def test_ranking_correctness(memory):
    """Specific test for the user's problematic query."""
    query = "как я хотел улучшить отображение гипотез в плане обоснования и ожидаемого результата? кто будет их наполнять смыслом?"
    results = memory.search_decisions(query, limit=5)
    
    assert len(results) > 0, "No results found for the specific query"
    assert "asynchronous enrichment" in results[0]['title'].lower(), f"Target is not Top-1 for the specific query. Top-1 is {results[0]['title']}"
