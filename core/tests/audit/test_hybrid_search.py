import os
import pytest
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import EmbeddingProvider

class SimpleMockProvider(EmbeddingProvider):
    def get_embedding(self, text: str):
        return [0.1] * 1536

def test_hybrid_search_policy(tmp_path):
    storage_path = str(tmp_path / "memory")
    
    # Use real memory logic with mock embeddings
    memory = Memory(
        storage_path=storage_path,
        embedding_provider=SimpleMockProvider()
    )
    
    # Recording first decision
    memory.record_decision("Version 1", "policy", "Old rule")
    old_id = memory.get_decisions()[0]
    
    # Superseding with second decision
    memory.supersede_decision("Version 2", "policy", "New rule", [old_id])
    
    # Searching for 'rule' in strict mode
    results = memory.search_decisions("rule", limit=10, mode="strict")
    
    for r in results:
        assert r['status'] == "active", f"PI Violation: Inactive decision {r['id']} returned in search!"

    assert len(results) == 1
    assert results[0]['status'] == "active"
