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

def test_deep_grounding_inheritance(temp_memory_path):
    """
    Ensures that a new decision version inherits links to all episodic events 
    associated with its predecessors.
    """
    memory = Memory(storage_path=temp_memory_path)
    target = "Inheritance-Test"
    
    # 1. Record an event with UNIQUE content
    ev_1 = MemoryEvent(source="agent", kind="result", content=f"Evidence 1 {uuid.uuid4()}")
    ev_id_1 = memory.episodic.append(ev_1)
    
    # Record initial decision V1 with evidence
    res_v1 = memory.record_decision(
        title="Decision V1", target=target, rationale="Base version.",
        evidence_ids=[ev_id_1]
    )
    fid_v1 = res_v1.metadata["file_id"]
    
    # 2. Record another event and link it to V1
    ev_2 = MemoryEvent(source="agent", kind="result", content=f"Evidence 2 {uuid.uuid4()}")
    ev_id_2 = memory.episodic.append(ev_2)
    memory.link_evidence(ev_id_2, fid_v1)
    
    # Verify V1 has 2 links
    links_v1 = memory.episodic.get_linked_event_ids(fid_v1)
    assert ev_id_1 in links_v1
    assert ev_id_2 in links_v1
    
    # 3. Supersede V1 with V2
    ev_3 = MemoryEvent(source="agent", kind="result", content=f"Evidence 3 {uuid.uuid4()}")
    ev_id_3 = memory.episodic.append(ev_3)
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

def test_arbiter_callback_logic_supersede(temp_memory_path):
    """Scenario 1: Arbiter decides to SUPERSEDE in the Gray Zone (0.5-0.7)."""
    memory = Memory(storage_path=temp_memory_path)
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
def test_arbiter_callback_logic_auto_supersede_over_0_7(temp_memory_path):
    """Scenario 2: Automatic supersede happens for sim > 0.7, ignoring arbiter."""
    memory = Memory(storage_path=temp_memory_path)
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

def test_hybrid_search_rrf_and_grounding_boost(temp_memory_path):
    """
    Ensures that RRF correctly fuses Keyword and Vector results, 
    and that 'Evidence Boost' elevates grounded decisions.
    """
    memory = Memory(storage_path=temp_memory_path)
    
    # 1. Record Decision A (Vector match + Grounding boost)
    res_a = memory.record_decision(
        title="Performance latency optimization and performance speed",
        target="perf-a",
        rationale="Performance performance performance performance performance."
    )
    fid_a = res_a.metadata["file_id"]
    
    # 2. Record Decision B (Keyword win)
    res_b = memory.record_decision(
        title="Performance Rules",
        target="perf-b",
        rationale="General guidelines for system behavior."
    )
    fid_b = res_b.metadata["file_id"]
    
    # 3. Add many evidence links to A to boost it significantly (+600%)
    for i in range(30):
        ev = MemoryEvent(source="agent", kind="result", content=f"Perf Evidence {uuid.uuid4()}")
        ev_id = memory.episodic.append(ev)
        memory.link_evidence(ev_id, fid_a)
    
    # 4. Search for 'performance'
    results = memory.search_decisions("performance", limit=2)
    
    assert len(results) >= 2
    top_id = results[0]['id']
    assert top_id == fid_a, f"Expected {fid_a} to be top due to boost, but got {top_id}. Scores: {[ (r['id'], r['score']) for r in results ]}"
    assert results[0]['evidence_count'] == 31

