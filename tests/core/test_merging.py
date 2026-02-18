import pytest
from unittest.mock import MagicMock, patch
from ledgermind.core.reasoning.merging import MergeEngine
from ledgermind.core.core.schemas import KIND_PROPOSAL

@pytest.fixture
def mock_memory():
    mem = MagicMock()
    mem.semantic.repo_path = "/tmp/fake_repo"
    return mem

@pytest.fixture
def merge_engine(mock_memory):
    return MergeEngine(mock_memory)

@patch("os.path.join")
@patch("builtins.open")
@patch("ledgermind.core.stores.semantic_store.loader.MemoryLoader.parse")
def test_scan_for_duplicates_creates_proposal(mock_parse, mock_open, mock_join, merge_engine, mock_memory):
    # Setup mock data
    mock_memory.get_decisions.return_value = ["dec1.md", "dec2.md"]
    
    # Mock file reading for dec1.md
    mock_parse.return_value = ({"content": "Same content", "context": {"title": "T1"}}, "Body")
    
    # Mock search results - found a duplicate
    mock_memory.search_decisions.return_value = [
        {"id": "dec2.md", "score": 0.99, "title": "T2"}
    ]
    
    # Mock proposal creation
    mock_memory.process_event.return_value = MagicMock(metadata={"file_id": "prop1.md"})
    
    proposals = merge_engine.scan_for_duplicates(threshold=0.90)
    
    assert len(proposals) == 1
    assert proposals[0] == "prop1.md"
    
    # Verify search was called with content from dec1.md
    mock_memory.search_decisions.assert_called_with("Same content", limit=5, mode="strict")
    
    # Verify proposal was created
    mock_memory.process_event.assert_called()
    args, kwargs = mock_memory.process_event.call_args
    assert kwargs["kind"] == KIND_PROPOSAL
    assert "dec1.md" in kwargs["context"].suggested_supersedes
    assert "dec2.md" in kwargs["context"].suggested_supersedes

@patch("os.path.join")
@patch("builtins.open")
@patch("ledgermind.core.stores.semantic_store.loader.MemoryLoader.parse")
def test_scan_for_duplicates_no_duplicates(mock_parse, mock_open, mock_join, merge_engine, mock_memory):
    mock_memory.get_decisions.return_value = ["dec1.md"]
    mock_parse.return_value = ({"content": "Unique content"}, "Body")
    mock_memory.search_decisions.return_value = []
    
    proposals = merge_engine.scan_for_duplicates()
    assert len(proposals) == 0
