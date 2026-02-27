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

