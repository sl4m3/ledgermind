import pytest
import os
import shutil
from ledgermind.core.api.bridge import IntegrationBridge

@pytest.fixture
def temp_memory_path(tmp_path):
    path = tmp_path / "bridge_test"
    return str(path)

@pytest.fixture
def bridge(temp_memory_path):
    return IntegrationBridge(memory_path=temp_memory_path)

def test_bridge_initialization(bridge, temp_memory_path):
    assert bridge.memory_path == os.path.abspath(temp_memory_path)
    assert os.path.exists(temp_memory_path)

def test_record_and_get_context(bridge):
    # Record a decision directly into memory to have context
    bridge.record_decision(
        title="Database Choice",
        target="db_engine",
        rationale="We use SQLite for simplicity in this project"
    )
    
    # Wait for vector indexing if it's async (it's sync currently)
    
    # Get context
    context = bridge.get_context_for_prompt("What database should I use?")
    assert "[LEDGERMIND KNOWLEDGE BASE ACTIVE]" in context
    assert "Database Choice" in context
    assert "SQLite" in context

def test_record_interaction(bridge):
    bridge.record_interaction(
        prompt="Tell me about the project",
        response="The project is called Ledgermind",
        success=True
    )
    
    # Verify events are in episodic memory
    events = bridge.memory.get_recent_events(limit=5)
    # Filter for our events
    prompts = [e for e in events if e['kind'] == 'prompt']
    results = [e for e in events if e['kind'] == 'result']
    
    assert len(prompts) >= 1
    assert prompts[0]['content'] == "Tell me about the project"
    assert len(results) >= 1
    assert results[0]['content'] == "The project is called Ledgermind"
    assert results[0]['context']['success'] is True

def test_get_stats(bridge):
    stats = bridge.get_stats()
    assert "health" in stats
    assert "semantic_count" in stats
    assert "episodic_count" in stats

def test_extended_core_interactions(bridge):
    """Test the new proxy methods added to IntegrationBridge."""
    
    # 1. Record Decision
    dec = bridge.record_decision(
        title="Test Decision", 
        target="test_target", 
        rationale="Rationale must be longer than 10 chars"
    )
    assert dec.should_persist is True
    dec_id = dec.metadata["file_id"]
    
    # 2. Get Decisions
    all_decs = bridge.get_decisions()
    assert dec_id in all_decs
    
    # 3. Search
    results = bridge.search_decisions("Test Decision")
    assert len(results) > 0
    assert results[0]['id'] == dec_id
    
    # 4. Supersede
    new_dec = bridge.supersede_decision(
        title="New Test Decision",
        target="test_target",
        rationale="Better rationale that is long enough",
        old_decision_ids=[dec_id]
    )
    assert new_dec.should_persist is True
    new_id = new_dec.metadata["file_id"]
    
    # 5. Get History
    hist = bridge.get_decision_history(dec_id) # Should show superseded
    # Implementation detail: exact history structure depends on audit provider
    
    # 6. Update
    bridge.update_decision(new_id, {"status": "deprecated"}, "Deprecating for test")
    
    # 7. Knowledge Graph
    mermaid = bridge.generate_knowledge_graph()
    assert "graph TD" in mermaid
    
    # 8. Forget
    bridge.forget(new_id)
    assert new_id not in bridge.get_decisions()
