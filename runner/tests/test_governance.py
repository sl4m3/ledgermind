import pytest
from unittest.mock import MagicMock, patch
from agent_memory_runner.governance import GovernanceEngine

@pytest.fixture
def mock_memory():
    with patch('agent_memory_runner.governance.Memory') as m:
        instance = m.return_value
        yield instance

def test_governance_init_payload():
    engine = GovernanceEngine("./tmp_mem")
    payload = engine.get_init_payload().decode()
    assert "SESSION START" in payload
    assert "Memory Governance: Level 3" in payload

def test_governance_transform_input(mock_memory):
    """Verify that user input is wrapped with memory context."""
    engine = GovernanceEngine("./tmp_mem")
    
    mock_item = MagicMock()
    mock_item.preview = "Use PostgreSQL"
    mock_item.id = "dec_1"
    mock_item.score = 0.95
    mock_memory.search_decisions.return_value = [mock_item]
    
    user_input = b"How should we store data?"
    transformed = engine.transform_input(user_input).decode()
    
    # Check for presence of key sections
    assert "MEMORY SNAPSHOT" in transformed
    assert "Use PostgreSQL" in transformed
    assert "USER QUERY" in transformed
    assert "How should we store data?" in transformed
    
    mock_memory.search_decisions.assert_called_with("How should we store data?", limit=5, mode="balanced")

def test_governance_short_input_no_transform():
    """Verify that very short inputs (like 'ls') are not transformed."""
    engine = GovernanceEngine("./tmp_mem")
    user_input = b"ls"
    transformed = engine.transform_input(user_input)
    assert transformed == user_input
