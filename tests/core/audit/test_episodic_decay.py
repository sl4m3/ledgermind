import pytest
import os
import sqlite3
from ledgermind.core.core.schemas import MemoryEvent

def test_D3_semantic_immunity(memory, temp_storage):
    """D3: Events linked to semantic decisions are NEVER pruned/archived."""
    # Add event
    eid = memory.episodic.append(MemoryEvent(source="agent", kind="result", content="Evidence"))
    # Link it
    memory.link_evidence(eid, "decision_1.md")
    
    # Make it ancient (before TTL)
    db_path = os.path.join(temp_storage, "episodic.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE events SET timestamp = '2000-01-01T00:00:00' WHERE id = ?", (eid,))
    
    # Run decay
    report = memory.run_decay()
    
    # Must be retained
    assert report.retained_by_link == 1
    assert report.archived == 0
    assert report.pruned == 0
    
    # Verify status is still active
    events = memory.episodic.query(status='active')
    assert any(e['id'] == eid for e in events)

def test_D2_dry_run(memory, temp_storage):
    """D2: Dry-run must not change physical state."""
    eid = memory.episodic.append(MemoryEvent(source="agent", kind="result", content="Trash"))
    
    db_path = os.path.join(temp_storage, "episodic.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE events SET timestamp = '2000-01-01T00:00:00' WHERE id = ?", (eid,))
    
    # Dry run
    report = memory.run_decay(dry_run=True)
    assert report.archived == 1
    
    # Verify physical status: STILL ACTIVE
    events = memory.episodic.query(status='active')
    assert any(e['id'] == eid for e in events)

def test_archive_to_prune_pipeline(memory, temp_storage):
    """Verify 2-step cleanup: Active -> Archived -> Pruned."""
    eid = memory.episodic.append(MemoryEvent(source="agent", kind="result", content="C"))
    db_path = os.path.join(temp_storage, "episodic.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE events SET timestamp = '2000-01-01T00:00:00' WHERE id = ?", (eid,))
    
    # Step 1: Active -> Archive
    report1 = memory.run_decay()
    assert report1.archived == 1
    
    # Step 2: Archived -> Prune
    report2 = memory.run_decay()
    assert report2.pruned == 1
    
    # Final check: physically gone
    events = memory.episodic.query(limit=100, status='archived')
    assert not any(e['id'] == eid for e in events)
