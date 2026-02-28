import pytest
from datetime import datetime, timedelta
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import DecisionPhase, DecisionVitality, KIND_INTERVENTION

def test_lifecycle_search_ranking(tmp_path):
    storage = str(tmp_path)
    memory = Memory(storage_path=storage)
    
    # 1. Create a CANONICAL but DORMANT decision
    memory.process_event(
        source="system",
        kind="decision",
        content="Old Truth",
        context={
            "decision_id": "old_1",
            "target": "web_old",
            "title": "Old Truth",
            "rationale": "This was the standard long ago.",
            "phase": DecisionPhase.CANONICAL,
            "vitality": DecisionVitality.DORMANT,
            "first_seen": datetime.now() - timedelta(days=100),
            "last_seen": datetime.now() - timedelta(days=40)
        }
    )
    
    # 2. Create an EMERGENT and ACTIVE decision
    memory.process_event(
        source="system",
        kind="decision",
        content="New Hotness",
        context={
            "decision_id": "new_1",
            "target": "web_new",
            "title": "New Hotness",
            "rationale": "This is emerging and active right now.",
            "phase": DecisionPhase.EMERGENT,
            "vitality": DecisionVitality.ACTIVE,
            "first_seen": datetime.now() - timedelta(days=2),
            "last_seen": datetime.now()
        }
    )
    
    # Search for "web" (Lengthened to force full hybrid path for weights testing)
    results = memory.search_decisions("web architecture technology standard legacy framework", mode="balanced")
    
    for r in results:
        print(f"DEBUG: Result: {r['title']}, Score: {r['score']}, Phase: {r.get('phase')}, Vitality: {r.get('vitality')}")
    
    # New Hotness should be higher than Old Truth despite Phase difference
    # CANONICAL(1.5) * DORMANT(0.2) = 0.3
    # EMERGENT(1.2) * ACTIVE(1.0) = 1.2
    assert "New Hotness" in results[0]['title']

def test_intervention_immediate_emergent(tmp_path):
    storage = str(tmp_path)
    memory = Memory(storage_path=storage)
    
    # Record an intervention
    res = memory.process_event(
        source="user",
        kind=KIND_INTERVENTION,
        content="Force architecture change",
        context={
            "target": "arch",
            "title": "Use Microservices",
            "rationale": "Mandatory for scale."
        }
    )
    
    assert res.should_persist
    fid = res.metadata["file_id"]
    
    # Verify it is EMERGENT immediately
    meta = memory.semantic.meta.get_by_fid(fid)
    assert meta['phase'] == 'emergent'
    assert meta['vitality'] == 'active'
    assert meta['target'] == 'arch'

def test_sql_schema_integrity(tmp_path):
    storage = str(tmp_path)
    memory = Memory(storage_path=storage)
    
    # Just perform one operation
    memory.record_decision("Test Decision", "test", "This is a long enough rationale for validation.")
    
    # Check if columns exist in SQLite
    import sqlite3
    db_path = f"{storage}/semantic/semantic_meta.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("PRAGMA table_info(semantic_meta)")
    columns = [row[1] for row in cursor.fetchall()]
    
    expected = ['phase', 'vitality', 'reinforcement_density', 'stability_score', 'coverage']
    for col in expected:
        assert col in columns, f"Column {col} missing in SQLite"
