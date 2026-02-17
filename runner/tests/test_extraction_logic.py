import pytest
import os
from unittest.mock import MagicMock, patch
from agent_memory_runner.extractor import MemoryExtractor

@pytest.fixture
def mock_memory():
    with patch('agent_memory_runner.extractor.Memory') as m:
        instance = m.return_value
        yield instance

def test_noise_filtering(mock_memory, tmp_path):
    """Verify that progress bars and protocol markers are filtered."""
    extractor = MemoryExtractor(str(tmp_path))
    
    # Simulate a chunk with a progress bar and a useful decision
    chunk = b"Thinking... [10%]\rThinking... [100%]\nDecision: Use SQLite.\n"
    extractor.process_chunk(chunk)
    
    # We call flush to ensure any pending buffers are processed
    extractor.flush()
    
    # Verify calls
    recorded_contents = [call.kwargs.get('content') for call in mock_memory.process_event.call_args_list]
    
    assert any("Decision: Use SQLite" in str(c) for c in recorded_contents if c)
    assert not any("Thinking" in str(c) for c in recorded_contents if c)

def test_ansi_stripping(mock_memory, tmp_path):
    """Verify that ANSI escape codes are removed before recording."""
    extractor = MemoryExtractor(str(tmp_path))
    
    # Green colored text
    chunk = b"\x1b[32mTarget: Backend\x1b[0m\n"
    extractor.process_chunk(chunk)
    extractor.flush()
    
    recorded_contents = [call.kwargs.get('content') for call in mock_memory.process_event.call_args_list]
    assert "Target: Backend" in recorded_contents
    assert "\x1b[32m" not in str(recorded_contents[0])
