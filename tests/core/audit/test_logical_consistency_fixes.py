import pytest
import os
import time
from datetime import datetime, timedelta
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import KIND_PROPOSAL, KIND_DECISION, MemoryEvent

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
    old_ts = (datetime.now() - timedelta(days=14)).isoformat()
    memory.semantic.meta._conn.execute(
        "UPDATE semantic_meta SET last_hit_at = ?, timestamp = ? WHERE fid IN (?, ?)",
        (old_ts, old_ts, fid_draft, fid_active)
    )
    
    memory.run_decay()
    
    meta_draft = memory.semantic.meta.get_by_fid(fid_draft)
    meta_active = memory.semantic.meta.get_by_fid(fid_active)
    
    assert meta_draft['confidence'] <= 0.61
    assert meta_active['confidence'] > 0.6

def test_reflection_self_clustering_prevention(memory):
    """Point 6: Verify reflection doesn't cluster its own proposals."""
    # 1. Add an event with source='reflection_engine'
    # These events should be ignored by the reflection logic to avoid feedback loops
    memory.episodic.append(MemoryEvent(
        source="reflection_engine",
        kind="proposal",
        content="Self-generated content",
        context={"target": "self_test"}
    ))
    
    # 2. Add some other events to trigger a cycle
    for _ in range(3):
        memory.episodic.append(MemoryEvent(
            source="agent",
            kind="call",
            content="Normal call",
            context={"target": "other_target"}
        ))
    
    # 3. Run reflection
    results, _ = memory.reflection_engine.run_cycle()
    
    # 4. Verify that 'self_test' was NOT created as a proposal
    # We check the results (file IDs of created proposals)
    all_metas = memory.semantic.meta.list_all()
    targets = [m.get('target') for m in all_metas]
    
    assert "self_test" not in targets, "Reflection should ignore its own generated events"
