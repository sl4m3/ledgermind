import pytest
from unittest.mock import MagicMock, ANY
from ledgermind.core.reasoning.merging import MergeEngine, MergeEngineFacade, MergeConfig
from ledgermind.core.reasoning.ranking.graph import KnowledgeGraphGenerator
from ledgermind.core.core.schemas import KIND_RESULT

def test_merging_scan(tmp_path):
    mock_memory = MagicMock()
    mock_meta = MagicMock()
    mock_memory.semantic.meta = mock_meta
    
    # 1. Setup metadata
    cand1 = {"fid": "dec1.md", "target": "t1", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "content": "Content"}
    cand2 = {"fid": "dec2.md", "target": "t1", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "content": "Content"}
    data = [cand1, cand2]
    mock_meta.list_all.return_value = data
    mock_meta.get_by_fid.side_effect = lambda fid: {"dec1.md": cand1, "dec2.md": cand2}.get(fid)
    
    # 2. Simulate resolve_to_truth
    mock_memory._resolve_to_truth.side_effect = lambda fid, mode, cache: cache.get(fid) if cache else None
    
    # 3. Simulate vector search
    mock_memory.vector.search.return_value = [
        {"id": "dec2.md", "score": 0.99}
    ]
    
    # 4. Initialize Facade
    config = MergeConfig(threshold=0.8)
    facade = MergeEngineFacade(mock_memory, config)
    
    # 5. Mock Algorithm to avoid vector math errors
    facade.algorithm = MagicMock()
    facade.algorithm.calculate_similarity.return_value = 0.95
    facade.algorithm._get_doc_text.return_value = "Content"
    
    # 6. Mock Transaction Manager
    facade.transaction_manager = MagicMock()
    facade.transaction_manager.get_active_targets.return_value = []
    facade.transaction_manager.create_proposal.return_value = "prop1.md"
    
    # 7. Run scan
    result = facade.scan_for_duplicates(data)
    
    assert result.success is True
    assert len(result.data) > 0
    assert result.data[0] == "prop1.md"

def test_graph_generation(tmp_path):
    mock_meta = MagicMock()
    mock_meta.list_all.return_value = [
        {"fid": "f1.md", "target": "target_one", "status": "active", "kind": "decision"},
        {"fid": "f2.md", "target": "target_one", "status": "superseded", "kind": "decision", "superseded_by": "f1.md"}
    ]
    
    generator = KnowledgeGraphGenerator(str(tmp_path), mock_meta)
    mermaid = generator.generate_mermaid()
    
    assert "graph TD" in mermaid
    assert "f1_md" in mermaid
    assert "f2_md" in mermaid
    assert "superseded by" in mermaid
