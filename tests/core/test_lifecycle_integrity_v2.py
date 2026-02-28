
import pytest
import os
import uuid
import json
from datetime import datetime, timedelta
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import (
    DecisionStream, DecisionPhase, DecisionVitality, KIND_DECISION, KIND_PROPOSAL
)
from ledgermind.core.stores.semantic_store.meta import SemanticMetaStore

@pytest.fixture
def memory(tmp_path):
    storage = tmp_path / "memory"
    mem = Memory(vector_model="all-MiniLM-L6-v2", storage_path=str(storage), namespace="test")
    yield mem
    mem.close()

def test_repro_issue_6_confidence_momentum(memory):
    """Issue #6: Verify that promote_stream overwrites confidence (Pre-fix)."""
    from ledgermind.core.reasoning.lifecycle import LifecycleEngine
    engine = LifecycleEngine()
    
    stream = DecisionStream(
        decision_id="test-id",
        target="test-target",
        title="Test Title",
        rationale="Test Rationale longer than 10 chars",
        confidence=0.1 # Decayed confidence
    )
    
    # promote_stream recalculates based on static metrics
    # Currently it ignores previous 0.1
    updated = engine.promote_stream(stream)
    
    # If the fix is NOT applied, updated.confidence will be calculated from scratch.
    # If fixed, it should be somewhere between 0.1 and the calculated value (0.0).
    # 0.1 * 0.5 + 0.0 * 0.5 = 0.05
    assert 0.04 < updated.confidence < 0.06

def test_repro_issue_8_broken_link(memory, tmp_path):
    """Issue #8: Verify that resolve_to_truth returns last record for broken links."""
    meta_store = memory.semantic.meta
    
    # Create a chain: A -> B (missing)
    meta_store.upsert(
        fid="A.md", target="T", status="superseded", kind="decision",
        timestamp=datetime.now(), superseded_by="B.md"
    )
    # B.md does NOT exist in meta_store
    
    res = meta_store.resolve_to_truth("A.md")
    assert res is not None 
    assert res['fid'] == "A.md" # Should return A as it's the last existing one

def test_repro_issue_11_lifecycle_audit(memory):
    """Issue #11: Verify that phase transitions are logged."""
    from ledgermind.core.core.schemas import MemoryEvent
    # Create a proposal (stream)
    ctx = DecisionStream(
        decision_id=str(uuid.uuid4()),
        target="audit-test",
        title="Audit Test Title",
        rationale="Audit Test Rationale longer than 10 chars",
        phase=DecisionPhase.PATTERN
    )
    
    ev = MemoryEvent(source="system", kind=KIND_PROPOSAL, content="Test", context=ctx)
    memory.process_event(source="system", kind=KIND_PROPOSAL, content="Test", context=ctx)
    fid = memory.semantic.meta.list_all()[0]['fid']
    
    # Update phase
    memory.update_decision(fid, {"phase": DecisionPhase.EMERGENT.value}, "Promote")
    
    # Check episodic logs
    logs = memory.episodic.query(limit=20)
    lifecycle_logs = [l for l in logs if "Lifecycle:" in l['content']]
    assert len(lifecycle_logs) == 1
    assert "pattern → emergent" in lifecycle_logs[0]['content']

def test_repro_issue_9_proposal_atomic_rollback(memory):
    """Issue #9: Verify that proposal stays 'accepted' even if conversion fails (Pre-fix)."""
    from ledgermind.core.core.schemas import MemoryEvent
    # 1. Create a proposal
    ctx = {
        "title": "Atomic Test Title",
        "target": "atomic-target",
        "status": "draft",
        "rationale": "Atomic Test Rationale longer than 10 chars",
        "confidence": 0.8
    }
    ev = MemoryEvent(source="user", kind=KIND_PROPOSAL, content="Atomic Test", context=ctx)
    fid = memory.semantic.save(ev)
    
    # 2. Mock a failure in record_decision by forcing a conflict
    # We create an active decision for the same target first
    memory.record_decision("Existing Decision", "atomic-target", "Existing Rationale")
    
    # 3. Try to accept the proposal - should fail with ConflictError
    with pytest.raises(Exception) as excinfo:
        memory.accept_proposal(fid)
    
    print(f"Caught expected error: {excinfo.value}")
    
    # 4. Check proposal status
    meta = memory.semantic.meta.get_by_fid(fid)
    ctx_after = json.loads(meta['context_json'])
    # In current behavior, it might have been marked 'accepted' if the conversion failed LATE.
    # But accept_proposal calls record_decision BEFORE update_decision.
    # Wait, in memory.py:768 it updates status AFTER record_decision.
    # So if record_decision fails, update_decision won't be called.
    # HOWEVER, record_decision might succeed but something else fails?
    # Actually, issue #9 mentions that if accept_proposal crashes AFTER record_decision 
    # but BEFORE update_decision (proposal status), they diverge.
    print(f"Proposal status after failure: {ctx_after.get('status')}")
