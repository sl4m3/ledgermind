import pytest
from unittest.mock import MagicMock, patch
import os
from agent_memory_runner.governance import GovernanceEngine

@pytest.fixture
def mock_memory():
    m = MagicMock()
    # Default mocks
    m.vector.model = MagicMock() # Mock the model property
    m.search_decisions.return_value = []
    m.get_recent_events.return_value = []
    return m

def test_governance_warmup(mock_memory):
    engine = GovernanceEngine("./tmp_mem")
    with patch.object(GovernanceEngine, 'memory', new_callable=lambda: mock_memory):
        assert engine.warmup() is True

def test_governance_transform_empty():
    engine = GovernanceEngine("./tmp_mem")
    assert engine.transform_input(b"") == b""
    assert engine.transform_input(b"   ") == b""
    assert engine.transform_input(b"\x1b[A") == b"" # ANSI sequence

def test_governance_transform_short():
    engine = GovernanceEngine("./tmp_mem")
    # Should be ignored (too short / no words)
    assert engine.transform_input(b"ls") == b""
    assert engine.transform_input(b"cd ..") == b""

def test_governance_transform_valid(mock_memory):
    engine = GovernanceEngine("./tmp_mem")
    
    # Mock search result
    mock_item = {'id': 'dec_1', 'preview': 'Content', 'score': 0.95}
    mock_memory.search_decisions.return_value = [mock_item]
    
    with patch.object(GovernanceEngine, 'memory', new_callable=lambda: mock_memory):
        with patch.object(GovernanceEngine, "_get_file_content", return_value="### Content"):
            # Input with valid words
            res = engine.transform_input(b"how does the mcp server work?")
            
            assert b"[VERIFIED KNOWLEDGE BASE ACTIVE]" in res
            assert b"### Content" in res
            # Ensure search was called with cleaned query
            args, _ = mock_memory.search_decisions.call_args
            assert "mcp server work" in args[0] # Regex cleanup check

def test_governance_ansi_stripping(mock_memory):
    engine = GovernanceEngine("./tmp_mem")
    
    # Mock search result so we get an injection if parsing works
    mock_item = {'id': 'dec_1', 'preview': 'Content', 'score': 0.95}
    mock_memory.search_decisions.return_value = [mock_item]

    with patch.object(GovernanceEngine, 'memory', new_callable=lambda: mock_memory):
        with patch.object(GovernanceEngine, "_get_file_content", return_value="### Content"):
            # Use specific ANSI codes that our regex targets (CSI)
            # ESC [ 31 m (Red) ... ESC [ 0 m (Reset)
            raw = b"\x1b[31mhow does the mcp server work?\x1b[0m"
            res = engine.transform_input(raw)
            
            # Should still find context
            assert b"[VERIFIED KNOWLEDGE BASE ACTIVE]" in res
