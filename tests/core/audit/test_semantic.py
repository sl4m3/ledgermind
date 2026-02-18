import pytest
import os
from ledgermind.core.api.memory import Memory
from ledgermind.core.stores.semantic_store.integrity import IntegrityViolation
from ledgermind.core.stores.semantic_store.transitions import TransitionError
from ledgermind.core.stores.semantic_store.loader import MemoryLoader
from datetime import datetime

def test_S1_multiple_active_targets(temp_storage):
    """S1: IntegrityViolation on multiple active decisions for same target."""
    sem_path = os.path.join(temp_storage, "semantic")
    os.makedirs(sem_path, exist_ok=True)
    
    # Добавляем обязательные поля
    base = {"kind": "decision", "source": "agent", "content": "Valid Content", "timestamp": datetime.now().isoformat()}
    
    d1 = {**base, "context": {"title": "Title 1", "target": "DB_Target", "status": "active", "rationale": "Rationale 1 is long enough"}}
    d2 = {**base, "context": {"title": "Title 2", "target": "DB_Target", "status": "active", "rationale": "Rationale 2 is long enough"}}
    
    with open(os.path.join(sem_path, "1.md"), "w") as f: f.write(MemoryLoader.stringify(d1, "D1"))
    with open(os.path.join(sem_path, "2.md"), "w") as f: f.write(MemoryLoader.stringify(d2, "D2"))
    
    with pytest.raises(IntegrityViolation) as excinfo:
        Memory(storage_path=temp_storage)
    assert "Multiple active decisions" in str(excinfo.value)

def test_S3_dangling_supersede(temp_storage):
    """S3: Fail-fast on dangling reference."""
    sem_path = os.path.join(temp_storage, "semantic")
    os.makedirs(sem_path, exist_ok=True)
    
    d1 = {
        "kind": "decision", "source": "agent", "content": "Decision Content", "timestamp": datetime.now().isoformat(),
        "context": {
            "title": "D1", "target": "TargetArea", "status": "superseded", 
            "rationale": "Rationale for dangling test", "superseded_by": "non_existent.md"
        }
    }
    with open(os.path.join(sem_path, "1.md"), "w") as f: f.write(MemoryLoader.stringify(d1))
    
    with pytest.raises(IntegrityViolation) as excinfo:
        Memory(storage_path=temp_storage)
    assert "Dangling reference" in str(excinfo.value)

def test_S4_supersede_cycle(temp_storage):
    """S5: Cycle detection in supersede graph."""
    sem_path = os.path.join(temp_storage, "semantic")
    os.makedirs(sem_path, exist_ok=True)
    
    ts = datetime.now().isoformat()
    # 1 -> 2 -> 1 (with correct backlinks to pass I3)
    d1 = {
        "kind": "decision", "source": "agent", "content": "D1 Content", "timestamp": ts,
        "context": {
            "title": "D1", "target": "TargetArea", "status": "superseded", 
            "rationale": "Rationale for cycle test 1", "supersedes": ["2.md"], "superseded_by": "2.md"
        }
    }
    d2 = {
        "kind": "decision", "source": "agent", "content": "D2 Content", "timestamp": ts,
        "context": {
            "title": "D2", "target": "TargetArea", "status": "superseded", 
            "rationale": "Rationale for cycle test 2", "supersedes": ["1.md"], "superseded_by": "1.md"
        }
    }
    
    with open(os.path.join(sem_path, "1.md"), "w") as f: f.write(MemoryLoader.stringify(d1))
    with open(os.path.join(sem_path, "2.md"), "w") as f: f.write(MemoryLoader.stringify(d2))
    
    with pytest.raises(IntegrityViolation) as excinfo:
        Memory(storage_path=temp_storage)
    assert "Cycle detected" in str(excinfo.value)

def test_T1_immutable_fields(memory):

    """T1: TransitionValidator blocks immutable field changes."""

    memory.record_decision(title="Orig", target="TargetArea", rationale="Original rationale string")

    files = memory.semantic.list_decisions()

    fid = files[0]

    

    with pytest.raises(TransitionError):

        memory.semantic.update_decision(fid, {"target": "NEW_TARGET_AREA"}, "Illegal update rationale string")
