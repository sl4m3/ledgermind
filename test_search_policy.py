import os
import sys
from datetime import datetime

# Add paths
sys.path.insert(0, os.path.abspath("core"))
sys.path.insert(0, os.path.abspath("multi"))

from agent_memory_core.api.memory import Memory
from agent_memory_multi.embeddings import MockEmbeddingProvider

def test_hybrid_search_policy():
    storage_path = "/data/data/com.termux/files/home/.gemini/tmp/test_search_policy"
    if not os.path.exists(storage_path):
        os.makedirs(storage_path, exist_ok=True)
    
    # Use real memory logic with mock embeddings
    memory = Memory(
        storage_path=storage_path,
        embedding_provider=MockEmbeddingProvider()
    )
    
    print("Recording first decision...")
    memory.record_decision("Version 1", "policy", "Old rule")
    old_id = memory.get_decisions()[0]
    
    print("Superseding with second decision...")
    memory.supersede_decision("Version 2", "policy", "New rule", [old_id])
    
    print("Searching for 'rule'...")
    results = memory.search_decisions("rule", limit=10)
    
    print(f"Results found: {len(results)}")
    for r in results:
        print(f" - ID: {r['id']}, Status: {r['status']}")
        assert r['status'] == "active", f"PI Violation: Inactive decision {r['id']} returned in search!"

    assert len(results) == 1
    print("Verification successful: Only active decisions returned.")

if __name__ == "__main__":
    test_hybrid_search_policy()
