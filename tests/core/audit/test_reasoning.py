import pytest
from unittest.mock import MagicMock
from ledgermind.core.reasoning.merging import MergeEngine
from ledgermind.core.reasoning.distillation import DistillationEngine
from ledgermind.core.reasoning.ranking.graph import KnowledgeGraphGenerator

def test_merging_scan(tmp_path):
    mock_memory = MagicMock()
    mock_memory.get_decisions.return_value = ["dec1.md", "dec2.md"]
    mock_memory.semantic.repo_path = str(tmp_path)
    
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
    
    engine = MergeEngine(mock_memory)
    proposals = engine.scan_for_duplicates(threshold=0.9)
    
    # Should create 2 proposals or just detect 
    assert len(proposals) > 0
    assert mock_memory.process_event.called

def test_distillation_success():
    mock_episodic = MagicMock()
    # Mocking successful trajectory
    mock_episodic.query.return_value = [
        {"id": 1, "kind": "result", "content": "Mission Success", "context": {"success": True, "target": "target_long_enough"}},
        {"id": 2, "kind": "task", "content": "Step 1", "context": {"rationale": "Do X"}},
        {"id": 3, "kind": "task", "content": "Step 2", "context": {"rationale": "Do Y"}}
    ]
    
    engine = DistillationEngine(mock_episodic)
    proposals = engine.distill_trajectories(limit=10)
    
    assert len(proposals) == 1
    assert "Procedural Optimization" in proposals[0].title
    assert len(proposals[0].procedural.steps) == 2

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
