import pytest
from unittest.mock import MagicMock
from ledgermind.core.reasoning.merging import MergeEngine
from ledgermind.core.reasoning.ranking.graph import KnowledgeGraphGenerator
from ledgermind.core.core.schemas import KIND_RESULT

def test_merging_scan(tmp_path):
    mock_memory = MagicMock()
    # Mock metadata store
    mock_meta = MagicMock()
    mock_memory.semantic.meta = mock_meta
    
    mock_memory.get_decisions.return_value = ["dec1.md", "dec2.md"]
    mock_memory.semantic.repo_path = str(tmp_path)
    
    # Mock list_all to return enriched candidates
    mock_meta.list_all.return_value = [
        {"fid": "dec1.md", "target": "t1", "status": "active", "kind": "decision", "enrichment_status": "completed"},
        {"fid": "dec2.md", "target": "t1", "status": "active", "kind": "decision", "enrichment_status": "completed"}
    ]
    
    # Create two identical files
    content = """---
kind: decision
content: Same Content
context: {title: Same, target: t1, status: active}
---
# Same Content"""
    
    (tmp_path / "dec1.md").write_text(content)
    (tmp_path / "dec2.md").write_text(content)
    
    # Mock search to return each other as duplicates
    mock_memory.search_decisions.side_effect = [
        [{"id": "dec2.md", "score": 0.99}], # dec1 -> dec2
        [{"id": "dec1.md", "score": 0.99}]  # dec2 -> dec1
    ]
    
    # Mock proposal creation
    mock_memory.process_event.return_value = MagicMock(metadata={"file_id": "prop1.md"})
    
    engine = MergeEngine(mock_memory)
    proposals = engine.scan_for_duplicates(threshold=0.9)
    
    # Should create proposals or detect
    assert len(proposals) > 0
    assert mock_memory.process_event.called

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
