import pytest
from unittest.mock import MagicMock
from ledgermind.core.reasoning.merging import MergeEngine

@pytest.fixture
def mock_memory():
    m = MagicMock()
    m.semantic.meta = MagicMock()
    return m

@pytest.fixture
def engine(mock_memory):
    return MergeEngine(mock_memory)

def test_architectural_guard_via_scan(engine, mock_memory):
    """Verify that scan_for_duplicates respects the Architectural Guard."""
    # 1. Setup two enriched documents with identical titles but different roots
    title = "Technical Refinement Protocol"
    mock_memory.semantic.meta.list_all.return_value = [
        {"fid": "core.md", "target": "core/logic", "title": title, "status": "active", "enrichment_status": "completed"},
        {"fid": "docs.md", "target": "docs/logic", "title": title, "status": "active", "enrichment_status": "completed"}
    ]
    
    # 2. Mock search to return the cross-root match
    mock_memory.search_decisions.return_value = [
        {"id": "docs.md", "target": "docs/logic", "title": title, "score": 1.0, "similarity_score": 1.0}
    ]
    
    # 3. Run scan
    proposals = engine.scan_for_duplicates(threshold=0.1)
    
    # Should be 0 because core/ and docs/ are different roots
    assert len(proposals) == 0

def test_jaccard_technical_precision(engine):
    """Verify that Jaccard handles technical keywords and titles correctly."""
    # Same title, different keywords
    t1 = "SQLite Buffer Management"
    kw1 = "sqlite, buffer, io"
    
    t2 = "SQLite Buffer Management"
    kw2 = "sqlite, buffer, cache"
    
    # Jaccard should be high but not 1.0
    j1 = engine._calculate_jaccard(t1, t2, "core/a", "core/a", kw1, kw2)
    
    # Completely different technical context
    t3 = "Network Socket Timeout"
    kw3 = "network, tcp, timeout"
    j2 = engine._calculate_jaccard(t1, t3, "core/a", "core/b", kw1, kw3)
    
    assert j1 > 0.7
    assert j2 < 0.2
