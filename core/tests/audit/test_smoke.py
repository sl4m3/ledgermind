import pytest
import os
from agent_memory_core.api.memory import Memory

def test_system_wide_smoke_check(temp_storage):
    """
    Comprehensive smoke test covering:
    1. Initialization
    2. Record & Search
    3. Knowledge Evolution (Supersede)
    4. Graph Generation
    5. Maintenance (Merge/Decay)
    """
    from .conftest import MockEmbeddingProvider
    
    # 1. Initialization
    memory = Memory(storage_path=temp_storage, embedding_provider=MockEmbeddingProvider())
    
    # 2. Record & Semantic Search
    res = memory.record_decision("Smoke Test Decision", "smoke_target", "Initial rationale for testing")
    doc_id = res.metadata.get("file_id")
    assert doc_id is not None
    
    results = memory.search_decisions("smoke test")
    assert len(results) > 0
    
    # 3. Supersede (Knowledge Evolution)
    memory.supersede_decision("Smoke Test V2", "smoke_target", "Updated rationale for evolution", [doc_id])
    
    # Search should now resolve to V2
    results_v2 = memory.search_decisions("smoke test", mode="strict")
    assert len(results_v2) == 1
    assert results_v2[0]['status'] == "active"
    assert "V2" in results_v2[0]['preview']
    
    # 4. Advanced Features: Graph Generation
    graph = memory.generate_knowledge_graph()
    assert "graph TD" in graph
    assert "smoke_target" in graph
    
    # 5. Advanced Features: Maintenance Engine
    report = memory.run_maintenance()
    assert "merging" in report
    assert "decay" in report

def test_enterprise_dependency_check():
    """Verify that core enterprise libraries are importable."""
    import sqlalchemy
    import pgvector
    assert sqlalchemy.__version__ is not None
    # pgvector doesn't have __version__, just checking import is enough
