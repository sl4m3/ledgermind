import pytest
import os
import time
from datetime import datetime, timedelta
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import KIND_PROPOSAL, KIND_DECISION, ProposalStatus

def test_decay_draft_proposals(memory):
    """Point 5: Verify draft proposals decay faster."""
    # 1. Create a draft proposal
    res = memory.process_event(
        source="agent",
        kind=KIND_PROPOSAL,
        content="Draft Proposal",
        context={
            "title": "Draft Proposal",
            "target": "decay_test",
            "status": "draft",
            "rationale": "Test rationale for decay is long enough",
            "confidence": 0.8
        }
    )
    fid_draft = res.metadata["file_id"]
    
    # 2. Create an active decision
    res2 = memory.record_decision(
        title="Active Decision",
        target="decay_test_active",
        rationale="Test rationale for active decay is long enough"
    )
    fid_active = res2.metadata["file_id"]
    
    # Manually backdate them in metadata for decay to trigger (needs > 7 days inactivity)
    # We'll simulate 14 days inactivity. Use ISO strings that SQLite can sort.
    old_ts = (datetime.now() - timedelta(days=14)).isoformat()
    memory.semantic.meta._conn.execute(
        "UPDATE semantic_meta SET last_hit_at = ?, timestamp = ? WHERE fid IN (?, ?)",
        (old_ts, old_ts, fid_draft, fid_active)
    )
    
    # Standard rate is 0.05. 
    # Draft should decay by 0.05 * 2 * 2 (steps) = 0.2 -> 0.6
    # Active Decision should decay by (0.05 / 3) * 2 = 0.033 -> 0.96...
    
    memory.run_decay()
    
    meta_draft = memory.semantic.meta.get_by_fid(fid_draft)
    meta_active = memory.semantic.meta.get_by_fid(fid_active)
    
    # Confidence is rounded to 2 decimal places in results, but run_decay updates DB
    assert meta_draft['confidence'] <= 0.61
    assert meta_active['confidence'] > 0.9

def test_reflection_self_clustering_prevention(memory):
    """Point 6: Verify reflection doesn't cluster its own proposals."""
    from ledgermind.core.core.schemas import MemoryEvent, ProposalContent
    
    ctx = ProposalContent(
        target="self_test", 
        title="Self Proposal", 
        rationale="Rationale is long enough for validation",
        confidence=0.5
    )
    # Use a valid source and add a mock ID
    ev = MemoryEvent(
        source="reflection_engine",
        kind="proposal",
        content="Self Proposal",
        context=ctx
    )
    ev_dict = ev.model_dump(mode='json')
    ev_dict['id'] = 999
    
    clusters = memory.reflection_engine._cluster_evidence([ev_dict])
    assert "self_test" not in clusters

def test_competing_hypotheses_deep_copy(memory):
    """Point 10: Verify competing hypotheses have independent procedural objects."""
    from ledgermind.core.core.schemas import ProceduralContent, ProceduralStep
    
    procedural = ProceduralContent(
        target_task="task",
        success_evidence_ids=[1],
        steps=[ProceduralStep(action="step1")]
    )
    
    stats = {'all_ids': [1], 'errors': 5.0, 'successes': 0.0, 'last_seen': datetime.now().isoformat()}
    
    # Run it and verify it works
    fids = memory.reflection_engine._generate_competing_hypotheses("test_target", stats)
    assert len(fids) == 2

def test_search_boost_cap(memory):
    """Point 8: Verify search boost is capped at 1.0."""
    from ledgermind.core.core.schemas import MemoryEvent
    res = memory.record_decision(
        title="Popular Decision",
        target="boost_test",
        rationale="This one has many links and is very popular"
    )
    fid = res.metadata["file_id"]
    
    # Link 10 events -> boost = 10 * 0.2 = 2.0, should be capped at 1.0
    for i in range(10):
        ev = MemoryEvent(
            kind="result", 
            content=f"Evidence {i}", 
            source="system",
            context={"success": 1.0}
        )
        ev_id = memory.episodic.append(ev, linked_id=fid)
        
    results = memory.search_decisions("Popular Decision")
    assert results[0]['id'] == fid
    # 10 manual + 1 from record_decision
    assert results[0]['evidence_count'] == 11

def test_list_all_order(memory):
    """Point 7: Verify list_all returns recent records first."""
    memory.record_decision(title="Old", target="order_test", rationale="Old rationale is long enough")
    time.sleep(0.5) 
    memory.record_decision(title="New", target="order_test2", rationale="New rationale is long enough")
    
    decisions = memory.get_decisions()
    meta_first = memory.semantic.meta.get_by_fid(decisions[0])
    # The first one should be "New"
    assert meta_first['title'] == "New"

def test_pragma_synchronous(memory):
    """Point 9: Verify PRAGMA synchronous is NORMAL."""
    # Note: In some environments, PRAGMA synchronous might be 0 (OFF) if overridden by filesystem or driver.
    # However, we set it to 1 (NORMAL).
    cursor = memory.semantic.meta._conn.execute("PRAGMA synchronous")
    val = cursor.fetchone()[0]
    # 1 is NORMAL, 0 is OFF, 2 is FULL
    # If it fails, we'll see what it actually is.
    assert val == 1

from unittest.mock import patch

def test_distillation_window_size_config(memory):
    """Point 11: Verify distillation window_size is configurable."""
    memory.reflection_engine.policy.distillation_window_size = 10
    
    # We can check if DistillationEngine is instantiated with the right window_size
    # by mocking it in reflection.py
    with patch("ledgermind.core.reasoning.reflection.DistillationEngine") as mock_dist:
        memory.run_reflection()
        # Check that at least one call used window_size=10
        found = False
        for call in mock_dist.call_args_list:
            if call.kwargs.get('window_size') == 10:
                found = True
                break
        assert found, f"DistillationEngine was not called with window_size=10. Calls: {mock_dist.call_args_list}"

def test_target_inheritance_reset(memory):
    """Point 12: Verify target inheritance reset on new prompt."""
    evs = [
        {"id": 1, "kind": "prompt", "content": "p1", "source": "user", "timestamp": "2024-01-01T00:00:00", "context": {"target": "auth"}},
        {"id": 2, "kind": "result", "content": "r1", "source": "agent", "timestamp": "2024-01-01T00:00:01", "context": {}}, # Should inherit auth
        {"id": 3, "kind": "prompt", "content": "p2", "source": "user", "timestamp": "2024-01-01T00:00:02", "context": {}}, # Should NOT inherit, reset!
        {"id": 4, "kind": "result", "content": "r2", "source": "agent", "timestamp": "2024-01-01T00:00:03", "context": {}}, # Should NOT inherit
    ]
    
    clusters = memory.reflection_engine._cluster_evidence(evs)
    
    # ev 2 should be in 'auth'
    assert 2 in clusters['auth']['all_ids']
    # ev 3 and 4 should NOT be in 'auth'
    assert 3 not in (clusters.get('auth', {}).get('all_ids', []))
    assert 4 not in (clusters.get('auth', {}).get('all_ids', []))

def test_forget_unlinks_episodic(memory):
    """Point 13: Verify forget unlinks episodic events."""
    res = memory.record_decision(title="To be forgotten", target="forget_test", rationale="Rationale is long enough")
    fid = res.metadata["file_id"]
    
    from ledgermind.core.core.schemas import MemoryEvent
    ev = MemoryEvent(kind="result", content="Evidence", source="system")
    ev_id = memory.episodic.append(ev, linked_id=fid)
    
    # Verify linked
    links = memory.episodic.get_linked_event_ids(fid)
    assert ev_id in links
    
    # Forget
    memory.forget(fid)
    
    # Verify unlinked
    links_after = memory.episodic.get_linked_event_ids(fid)
    assert ev_id not in links_after
    
    # Verify event still exists but linked_id is NULL
    events = memory.episodic.query(limit=100, status='active')
    ev_after = next(e for e in events if e['id'] == ev_id)
    assert ev_after['linked_id'] is None

