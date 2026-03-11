import pytest
import uuid
from datetime import datetime
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import DecisionStream, DecisionPhase, KIND_PROPOSAL

@pytest.fixture
def memory(tmp_path):
    storage = str(tmp_path / "lifecycle_mem")
    return Memory(storage_path=storage)

def test_repro_issue_8_broken_link(memory):
    """Issue #8: Verify that resolve_to_truth returns last record for broken links."""
    meta_store = memory.semantic.meta
    
    # Create a chain: A -> B (missing)
    # V7.0: upsert requires title, content, and context_json
    meta_store.upsert(
        fid="A.md", target="T", title="A", status="superseded", kind="decision",
        timestamp=datetime.now(), content="A", context_json="{}",
        superseded_by="B.md"
    )
    # B.md does NOT exist in meta_store
    
    print(f'DEBUG METASTORE: {meta_store.get_by_fid("A.md")}')
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
    
    # Record it
    memory.process_event(source="system", kind=KIND_PROPOSAL, content="Test", context=ctx)
    fid = memory.semantic.meta.list_all()[0]['fid']
    
    # Update phase
    memory.update_decision(fid, {"phase": DecisionPhase.EMERGENT.value}, "Promote")
    
    # Check episodic logs
    # V7.0: Uses MemoryEvent with content "Lifecycle change for ..."
    logs = memory.episodic.query(limit=20)
    lifecycle_logs = [l for l in logs if "Lifecycle change" in l['content']]
    assert len(lifecycle_logs) == 1
