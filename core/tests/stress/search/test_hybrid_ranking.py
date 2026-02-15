import pytest
import os
import time
from datetime import datetime, timedelta
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import EmbeddingProvider

class MockEmbeddings(EmbeddingProvider):
    def get_embedding(self, text: str):
        return [0.1] * 384 # Simple mock

@pytest.fixture
def memory_fixture(tmp_path):
    storage = tmp_path / "search_mem"
    os.makedirs(storage, exist_ok=True)
    return Memory(storage_path=str(storage), embedding_provider=MockEmbeddings())

def test_hybrid_search_ranking(memory_fixture):
    """
    Verifies the RankingPolicy logic:
    1. Active decisions rank higher than superseded ones (Truth Bias).
    2. Superseded decisions are suppressed but present in 'audit' mode.
    """
    mem = memory_fixture
    target = "auth_system"
    
    # 1. Create initial decision (will become superseded)
    d1 = mem.record_decision("Auth V1", target, "Using Basic Authentication method (insecure)")
    doc_id_v1 = d1.metadata["file_id"]
    
    # 2. Supersede it (V2 is active)
    d2 = mem.supersede_decision("Auth V2", target, "Switching to OAuth2 for better security and token management", [doc_id_v1])
    doc_id_v2 = d2.metadata["file_id"]
    
    # 3. Search in 'balanced' mode (should prefer V2)
    results = mem.search_decisions("auth", limit=5, mode="balanced")
    
    assert len(results) > 0
    top_result = results[0]
    
    # Active V2 must be top, even if V1 vector score is identical
    assert top_result["id"] == doc_id_v2
    assert top_result["status"] == "active"
    
    # Verify V1 is NOT in results (or ranked very low/deduplicated)
    v1_in_results = any(r["id"] == doc_id_v1 for r in results)
    assert not v1_in_results, "Superseded decision should be deduplicated/hidden in balanced mode if active exists"

def test_audit_search_completeness(memory_fixture):
    """
    Verifies that 'audit' mode returns full history, including deprecated items.
    """
    mem = memory_fixture
    target = "api_version"
    
    d1 = mem.record_decision("API v1", target, "Using REST API for initial version")
    d2 = mem.supersede_decision("API v2", target, "Switching to GraphQL for flexibility", [d1.metadata["file_id"]])
    
    results = mem.search_decisions("api", limit=10, mode="audit")
    
    ids = [r["id"] for r in results]
    assert d1.metadata["file_id"] in ids
    assert d2.metadata["file_id"] in ids
    
    # Check scores: active should be higher
    s1 = next(r["score"] for r in results if r["id"] == d1.metadata["file_id"])
    s2 = next(r["score"] for r in results if r["id"] == d2.metadata["file_id"])
    assert s2 > s1
