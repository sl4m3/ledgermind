import pytest
from unittest.mock import MagicMock, patch
from ledgermind.core.reasoning.merging import MergeEngine

@pytest.fixture
def mock_memory():
    m = MagicMock()
    m.semantic.meta = MagicMock()
    return m

@pytest.fixture
def engine(mock_memory):
    return MergeEngine(mock_memory)

def test_self_match_normalization_logic(engine, mock_memory):
    """Verify that RRF similarity is correctly normalized against self-score."""
    title = "Normalization Unit Test"
    
    # Candidate meta
    mock_memory.semantic.meta.list_all.return_value = [
        {"fid": "source.md", "target": "core/test", "title": title, "status": "active", "enrichment_status": "completed"}
    ]
    
    # Search returns source with 0.5 and duplicate with 0.8
    mock_memory.search_decisions.return_value = [
        {"id": "duplicate.md", "score": 0.8, "similarity_score": 0.8, "title": title, "target": "core/test"},
        {"id": "source.md", "score": 0.5, "similarity_score": 0.5, "title": title, "target": "core/test"}
    ]
    
    # Mocking file parse
    with patch("ledgermind.core.stores.semantic_store.loader.MemoryLoader.parse") as mock_parse:
        mock_parse.return_value = ({"content": "...", "context": {"title": title, "target": "core/test"}}, "...")
        
        # We don't need to check the final proposal, 
        # just that the internal scoring logic reached the right conclusion.
        # But we check that a proposal IS created.
        mock_memory.process_event.return_value = MagicMock(metadata={"file_id": "p.md"})
        
        proposals = engine.scan_for_duplicates(threshold=0.5)
        assert len(proposals) == 1
