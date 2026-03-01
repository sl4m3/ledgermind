import os
import pytest
import uuid
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import KIND_DECISION, MemoryEvent
from ledgermind.core.core.exceptions import ConflictError

@pytest.fixture
def temp_memory_path(tmp_path):
    path = tmp_path / "memory"
    os.makedirs(path, exist_ok=True)
    return str(path)

def test_deep_grounding_inheritance(temp_memory_path, monkeypatch):
    """
    Ensures that a new decision version inherits links to all episodic events 
    associated with its predecessors.
    """
    from ledgermind.core.stores import vector
    from ledgermind.core.stores.vector import _MODEL_CACHE
    monkeypatch.setattr(vector, "EMBEDDING_AVAILABLE", False)
    
    memory = Memory(storage_path=temp_memory_path, vector_model=None)
    target = "Inheritance-Test"
    
    # 1. Record an event with UNIQUE content
    ev_1 = MemoryEvent(source="agent", kind="result", content=f"Evidence 1 {uuid.uuid4()}")
    ev_id_1 = memory.episodic.append(ev_1).value
    
    # Record initial decision V1 with evidence
    res_v1 = memory.record_decision(
        title="Decision V1", target=target, rationale="Base version.",
        evidence_ids=[ev_id_1]
    )
    fid_v1 = res_v1.metadata["file_id"]
    
    # 2. Record another event and link it to V1
    ev_2 = MemoryEvent(source="agent", kind="result", content=f"Evidence 2 {uuid.uuid4()}")
    ev_id_2 = memory.episodic.append(ev_2).value
    memory.link_evidence(ev_id_2, fid_v1)
    
    # Verify V1 has 2 links
    links_v1 = memory.episodic.get_linked_event_ids(fid_v1)
    assert ev_id_1 in links_v1
    assert ev_id_2 in links_v1
    
    # 3. Supersede V1 with V2
    ev_3 = MemoryEvent(source="agent", kind="result", content=f"Evidence 3 {uuid.uuid4()}")
    ev_id_3 = memory.episodic.append(ev_3).value
    res_v2 = memory.supersede_decision(
        title="Decision V2", target=target, rationale="Evolved version.",
        old_decision_ids=[fid_v1],
        evidence_ids=[ev_id_3]
    )
    fid_v2 = res_v2.metadata["file_id"]
    
    # 4. Verify Inheritance: V2 should have all 3 links
    links_v2 = memory.episodic.get_linked_event_ids(fid_v2)
    assert ev_id_1 in links_v2
    assert ev_id_2 in links_v2
    assert ev_id_3 in links_v2
    assert len(links_v2) >= 3

def test_arbiter_callback_logic_supersede(temp_memory_path, monkeypatch):
    """Scenario 1: Arbiter decides to SUPERSEDE in the Gray Zone (0.5-0.7)."""
    import numpy as np
    from unittest.mock import MagicMock
    from ledgermind.core.stores import vector
    from ledgermind.core.stores.vector import _MODEL_CACHE
    
    # Mock the vector model to return controlled similarity (0.6)
    mock_model = MagicMock()
    v1 = np.zeros(384, dtype='float32'); v1[0] = 1.0
    v2 = np.zeros(384, dtype='float32'); v2[0] = 0.6; v2[1] = 0.8 # Cosine sim = 0.6
    
    def mock_encode(texts, **kwargs):
        t = texts[0] if isinstance(texts, list) else texts
        if "maintenance" in t:
            return np.array([v1])
        return np.array([v2])

    mock_model.encode.side_effect = mock_encode
    mock_model.get_sentence_embedding_dimension.return_value = 384
    
    monkeypatch.setattr("ledgermind.core.stores.vector.EMBEDDING_AVAILABLE", True)
    from ledgermind.core.stores.vector import _MODEL_CACHE
    _MODEL_CACHE["mock-model"] = mock_model
    
    memory = Memory(storage_path=temp_memory_path, vector_model="mock-model")
    target = "Arbiter-Supersede"
    
    # Common core context to stabilize similarity
    core = "Standard procedures for maintaining and ensuring high system reliability and performance across all server nodes and backend services."
    
    # Domain A: Maintenance Focus
    memory.record_decision(
        title="Server infrastructure maintenance and scaling rules", 
        target=target, 
        rationale=f"{core} This focus is on hardware stability, patch management, and node availability."
    )
    
    arbiter_called = False
    def arbiter(n, o): 
        nonlocal arbiter_called
        arbiter_called = True
        return "SUPERSEDE"
    
    # Domain B: Deployment Focus (Highly related, shared 'core' text)
    memory.record_decision(
        title="Application layer deployment and monitoring rules", 
        target=target, 
        rationale=f"{core} This focus is on software rollout automation, CI/CD pipelines, and metrics collection.", 
        arbiter_callback=arbiter
    )
    
    assert arbiter_called, "Arbiter should be called in gray zone"
def test_arbiter_callback_logic_auto_supersede_over_0_7(temp_memory_path, monkeypatch):
    """Scenario 2: Automatic supersede happens for sim > 0.7, ignoring arbiter."""
    import numpy as np
    from unittest.mock import MagicMock
    from ledgermind.core.stores import vector
    from ledgermind.core.stores.vector import _MODEL_CACHE
    
    mock_model = MagicMock()
    # Support multiple calls: record A, record B, supersede
    mock_model.encode.return_value = np.array([[1.0] * 384], dtype='float32')
    mock_model.get_sentence_embedding_dimension.return_value = 384
    
    monkeypatch.setattr("ledgermind.core.stores.vector.EMBEDDING_AVAILABLE", True)
    from ledgermind.core.stores.vector import _MODEL_CACHE
    _MODEL_CACHE["mock-model-high"] = mock_model
    
    memory = Memory(storage_path=temp_memory_path, vector_model="mock-model-high")
    target = "Arbiter-Auto"
    
    # Titles almost identical to hit > 0.7
    common_title = "Core Architecture Choice"
    common_rationale = "Monolithic design selected for speed and efficiency."
    
    memory.record_decision(
        title=f"{common_title} A", 
        target=target, 
        rationale=common_rationale
    )
    
    arbiter_called = False
    def arbiter(n, o):
        nonlocal arbiter_called
        arbiter_called = True
        return "REJECT" 
    
    memory.record_decision(
        title=f"{common_title} B", 
        target=target, 
        rationale=common_rationale, 
        arbiter_callback=arbiter
    )
    
    assert not arbiter_called, "Arbiter should NOT be called for sim > 0.7"
    results = memory.search_decisions(target, mode="audit")
    assert any(r['title'] == f"{common_title} B" and r['status'] == 'active' for r in results)

def test_hybrid_search_rrf_and_grounding_boost(temp_memory_path, monkeypatch):
    """
    Ensures that RRF correctly fuses Keyword and Vector results, 
    and that 'Evidence Boost' elevates grounded decisions.
    """
    from ledgermind.core.stores import vector
    from ledgermind.core.stores.vector import _MODEL_CACHE
    monkeypatch.setattr(vector, "EMBEDDING_AVAILABLE", False)
    
    memory = Memory(storage_path=temp_memory_path, vector_model=None)
    
    # 1. Record Decision A (Vector match + Grounding boost)
    res_a = memory.record_decision(
        title="Performance latency optimization and performance speed",
        target="perf-a",
        rationale="Performance performance performance performance performance."
    )
    fid_a = res_a.metadata["file_id"]
    
    # 2. Record Decision B (Less relevant to 'performance' query)
    res_b = memory.record_decision(
        title="System Availability Rules and minimal performance",
        target="availability-b",
        rationale="General guidelines for high uptime and reliability."
    )
    fid_b = res_b.metadata["file_id"]
    
    # 3. Add a few evidence links to A to boost it (+60%)
    for i in range(3):
        ev = MemoryEvent(source="agent", kind="result", content=f"Perf Evidence {uuid.uuid4()}")
        ev_id = memory.episodic.append(ev).value
        memory.link_evidence(ev_id, fid_a)
    # 4. Search for 'performance' (Lengthened to force full hybrid path for RRF testing)
    results = memory.search_decisions("performance optimization latency speed scaling throughput", limit=2)
    
    assert len(results) >= 2
    top_id = results[0]['id']
    assert top_id == fid_a, f"Expected {fid_a} to be top due to boost, but got {top_id}. Scores: {[ (r['id'], r['score']) for r in results ]}"
    # 3 evidence links + 1 self-link from recording
    assert results[0]['evidence_count'] == 4
