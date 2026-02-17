import pytest
from unittest.mock import MagicMock, patch
from agent_memory_runner.governance import GovernanceEngine

@pytest.fixture
def mock_memory():
    with patch("agent_memory_runner.governance.Memory") as mock:
        yield mock.return_value

def test_governance_init_payload():
    engine = GovernanceEngine("./tmp_mem")
    payload = engine.get_init_payload().decode()
    assert "SESSION START" in payload
    assert "Audit Layer" in payload

def test_governance_transform_input(mock_memory):
    """Verify that user input is wrapped with verified knowledge base."""
    engine = GovernanceEngine("./tmp_mem")

    mock_item = {'id': 'dec_1', 'preview': 'Use PostgreSQL', 'score': 0.95}
    mock_memory.search_decisions.return_value = [mock_item]
    
    # We need to mock the file reading as well for the full content injection
    with patch.object(GovernanceEngine, "_get_file_content", return_value="### Title\nRationale: Use Postgres"):
        user_input = b"How should we store data?"
        transformed = engine.transform_input(user_input).decode()

        # Check for presence of key sections in v2.4.3
        assert "VERIFIED KNOWLEDGE BASE" in transformed
        assert "Rationale: Use Postgres" in transformed

def test_governance_cooldown(mock_memory):
    """Verify that knowledge is not injected if it is on cooldown (6h window)."""
    engine = GovernanceEngine("./tmp_mem")
    
    mock_item = {'id': 'dec_1', 'preview': 'Content', 'score': 0.95}
    mock_memory.search_decisions.return_value = [mock_item]
    
    # Simulate dec_1 being in recent episodic events (on cooldown - 1h ago)
    from datetime import datetime, timedelta
    ts = (datetime.now() - timedelta(hours=1)).isoformat()
    mock_memory.get_recent_events.return_value = [
        {'kind': 'context_injection', 'content': f'dec_1 @ {ts}', 'context': {'fid': 'dec_1'}}
    ]
    
    with patch.object(GovernanceEngine, "_get_file_content", return_value="Some Content"):
        # Use a long enough query with a space to bypass the new safety threshold
        transformed = engine.transform_input(b"This is a long test query for context.")
        # Should be empty because the only relevant item is on cooldown
        assert transformed == b""
        
        # Verify it checks episodic memory
        assert mock_memory.get_recent_events.called

def test_governance_relevance_threshold(mock_memory):
    """Verify that low relevance items are filtered out."""
    engine = GovernanceEngine("./tmp_mem")
    
    # Score below threshold (0.55)
    mock_item = {'id': 'dec_low', 'score': 0.4}
    mock_memory.search_decisions.return_value = [mock_item]
    mock_memory.get_recent_events.return_value = []
    
    transformed = engine.transform_input(b"This is a long test query for relevance.")
    assert transformed == b""

def test_governance_no_nudge_on_empty(mock_memory):
    """Verify that no nudge is provided when no context is found (nudge removed in v2.4.3)."""
    engine = GovernanceEngine("./tmp_mem")
    mock_memory.search_decisions.return_value = []
    
    # Even with random triggered, it should be empty
    transformed = engine.transform_input(b"New Topic Query that is long enough.")
    assert transformed == b""

def test_governance_no_duplicate_spam(mock_memory):
    """Regression test: verify that the same query does not trigger spam twice."""
    engine = GovernanceEngine("./tmp_mem", cooldown_limit=15)
    
    fid = "decision_123.md"
    mock_item = {'id': fid, 'score': 0.99}
    mock_memory.search_decisions.return_value = [mock_item]
    
    # State: First call, nothing on cooldown
    mock_memory.get_recent_events.return_value = []
    
    with patch.object(GovernanceEngine, "_get_file_content", return_value="Knowledge content"):
        # First call should succeed
        query = b"How to scale git repositories?"
        res1 = engine.transform_input(query)
        assert b"Knowledge content" in res1
        
        # Verify it recorded the injection
        assert mock_memory.process_event.called
        
        # State: Second call, knowledge is now on cooldown
        # In reality, Memory would now return this in get_recent_events
        from datetime import datetime
        ts = datetime.now().isoformat()
        mock_memory.get_recent_events.return_value = [
            {'kind': 'context_injection', 'content': f"{fid} @ {ts}", 'context': {'fid': fid}}
        ]
        
        # Second call should be empty
        res2 = engine.transform_input(query)
        assert res2 == b""
