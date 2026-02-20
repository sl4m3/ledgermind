import pytest
import os
import shutil
import time
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import TrustBoundary, MemoryEvent
from pydantic import ValidationError

def test_replay_determinism(temp_storage):

    """Verify that state is perfectly reconstructed from disk."""

    mem1 = Memory(storage_path=temp_storage)

    res = mem1.record_decision(title="D1", target="TargetArea", rationale="Rationale string must be long enough")

    

    # Add episodic event and link it

    event = MemoryEvent(source="agent", kind="result", content="Evidence of result")

    eid = mem1.episodic.append(event)

    

    # Simulate linking to a specific decision file

    files = mem1.get_decisions()

    fid = files[0]

    mem1.link_evidence(eid, fid)

    

    # Shutdown

    del mem1

    

    # Reload

    mem2 = Memory(storage_path=temp_storage)

    

    # Check Semantic

    decisions = mem2.get_decisions()

    assert fid in decisions

    

    # Check Episodic Immortality

    events = mem2.episodic.query(limit=10)

    e = next(e for e in events if e['id'] == eid)

    assert e['linked_id'] == fid

    print("Replay determinism verified.")



def test_trust_boundary_bypass_attempt(temp_storage):

    """Verify that direct store access is also protected by TrustBoundary."""

    memory = Memory(storage_path=temp_storage, trust_boundary=TrustBoundary.HUMAN_ONLY)

    

    # Direct save attempt on store (valid structure, but unauthorized source)

    event = MemoryEvent(

        source="agent", 

        kind="decision", 

        content="Hacked Decision",

        context={"title": "Hack", "target": "TargetArea", "rationale": "Hacking rationale must be long"}

    )

    

    with pytest.raises(PermissionError) as excinfo:

        memory.semantic.save(event)

    assert "Trust Boundary Violation" in str(excinfo.value)

    

    # Direct update attempt on store

    with pytest.raises(PermissionError) as excinfo:

        memory.semantic.update_decision("any.md", {"status": "superseded"}, "Hacked Update rationale must be long enough")

    assert "Trust Boundary Violation" in str(excinfo.value)



def test_false_conflict_on_load(temp_storage):

    """Verify loader doesn't find conflict between active and superseded decisions on start."""

    memory = Memory(storage_path=temp_storage)

    memory.record_decision(title="Old", target="Database", rationale="Old rationale for database")

    files = memory.get_decisions()

    fid1 = files[0]

    

    time.sleep(1.1)

    # Supersede it

    memory.supersede_decision(title="New", target="Database", rationale="New rationale for database evolution", old_decision_ids=[fid1])

    

    # Restart

    try:

        new_memory = Memory(storage_path=temp_storage)

        active_files = new_memory.semantic.list_active_conflicts("Database")

        assert len(active_files) == 1

        print("False conflict check passed.")

    except Exception as e:

        pytest.fail(f"Cold start failed: {e}")



def test_negative_capability_empty_fields(memory):

    """Verify that empty target or rationale is blocked by Pydantic."""

    # Empty target should raise ValidationError (via field_validator)

    with pytest.raises((ValidationError, ValueError)):

        memory.record_decision(title="Test", target="  ", rationale="Something long enough")

        

    # Empty rationale

    with pytest.raises((ValidationError, ValueError)):

        memory.record_decision(title="Test", target="TargetArea", rationale="")

    

    # Empty content in process_event

    with pytest.raises(ValidationError):

        memory.process_event(source="user", kind="result", content=" ")
