import pytest
from unittest.mock import MagicMock, patch
from ledgermind.core.reasoning.merging import MergeEngine

@pytest.fixture
def mock_memory():
    m = MagicMock()
    m.semantic.meta = MagicMock()
    # Meta Store should have the candidates
    m.semantic.meta.get_by_fid.side_effect = lambda fid: {
        "source.md": {"fid": "source.md", "target": "core/test", "title": "Normalization Unit Test", "status": "active", "enrichment_status": "completed", "merge_status": "idle"},
        "duplicate.md": {"fid": "duplicate.md", "target": "core/test", "title": "Normalization Unit Test", "status": "active", "enrichment_status": "completed", "merge_status": "idle"}
    }.get(fid)
    
    # Simulate resolve_to_truth
    m._resolve_to_truth.side_effect = lambda fid, mode, cache: {
        "source.md": {"fid": "source.md", "target": "core/test", "title": "Normalization Unit Test", "status": "active", "enrichment_status": "completed", "merge_status": "idle"},
        "duplicate.md": {"fid": "duplicate.md", "target": "core/test", "title": "Normalization Unit Test", "status": "active", "enrichment_status": "completed", "merge_status": "idle"}
    }.get(fid)
    
    return m

@pytest.fixture
def engine(mock_memory):
    return MergeEngine(mock_memory)

def test_self_match_normalization_logic(engine, mock_memory):
    """Verify that merge engine detects duplicates when they exceed threshold."""
    title = "Normalization Unit Test"
    
    # 1. Candidate meta (the list of items to scan)
    mock_memory.semantic.meta.list_all.return_value = [
        {"fid": "source.md", "target": "core/test", "title": title, "status": "active", "enrichment_status": "completed", "merge_status": "idle"}
    ]
    
    # 2. Vector Search returns possible matches
    mock_memory.vector.search.return_value = [
        {"id": "duplicate.md", "score": 0.8}
    ]
    
    # 3. Algorithm calculates similarity
    # We patch the algorithm created inside MergeEngineFacade
    with patch("ledgermind.core.reasoning.merging.facade.AlgorithmFactory.create") as mock_factory:
        mock_alg = MagicMock()
        # Ensure it returns > threshold for the duplicate
        mock_alg.calculate_similarity.return_value = 0.9
        mock_alg._get_doc_text.return_value = "Content"
        mock_factory.return_value = mock_alg
        
        # Re-initialize facade to use our mocked algorithm
        engine._facade.algorithm = mock_alg
        
        # Mocking file parse (not needed for facade but good for safety)
        with patch("ledgermind.core.stores.semantic_store.loader.MemoryLoader.parse") as mock_parse:
            mock_parse.return_value = ({"content": "...", "context": {"title": title, "target": "core/test"}}, "...")
            
            # Mocking process_event/supersede_decision to return a proposal fid
            mock_memory.supersede_decision.return_value = MagicMock(metadata={"file_id": "p.md"})
            
            proposals = engine.scan_for_duplicates(threshold=0.5)
            
            # Proposals should contain one FID from transaction manager
            assert len(proposals) == 1
