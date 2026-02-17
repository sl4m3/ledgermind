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

        # Check for presence of key sections in v2.4.0
        assert "VERIFIED KNOWLEDGE BASE" in transformed
        assert "Rationale: Use Postgres" in transformed

def test_governance_short_input_no_transform():
    """Verify that very short inputs (like 'ls') return empty bytes to skip injection."""
    engine = GovernanceEngine("./tmp_mem")
    user_input = b"ls"
    transformed = engine.transform_input(user_input)
    # In v2.4.0, we return b"" for short inputs to signal "no injection needed"
    assert transformed == b""
