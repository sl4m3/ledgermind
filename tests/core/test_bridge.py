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
    bridge.memory.record_decision(
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
