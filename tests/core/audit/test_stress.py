import pytest
import os
import subprocess
from ledgermind.core.api.memory import Memory
from ledgermind.core.stores.semantic_store.integrity import IntegrityViolation

def test_recovery_untracked_file(temp_storage):
    """Verify that untracked files (left after a crash) are recovered on next start."""
    # 1. Initialize
    memory = Memory(storage_path=temp_storage)
    sem_path = os.path.join(temp_storage, "semantic")
    
    # 2. Simulate crash: write valid MD file but don't git add/commit
    fake_file = "decision_crash_recovery.md"
    content = """---
kind: decision
source: agent
content: Recovered Decision
timestamp: '2026-02-15T00:00:00'
context:
  title: Recovered
  target: recovery_test
  status: active
  rationale: This file was created during a simulated crash.
---
# Recovered Decision"""
    
    with open(os.path.join(sem_path, fake_file), 'w') as f:
        f.write(content)
        
    # Verify it is untracked
    status_before = subprocess.run(["git", "status", "--short"], cwd=sem_path, capture_output=True, text=True).stdout
    assert fake_file in status_before
    
    # 3. Reload Memory. Recovery Engine should kick in.
    new_memory = Memory(storage_path=temp_storage)
    
    # 4. Verify recovery
    status_after = subprocess.run(["git", "status", "--short"], cwd=sem_path, capture_output=True, text=True).stdout
    assert fake_file not in status_after
    assert fake_file in new_memory.get_decisions()
    print("Crash recovery successful.")

def test_isolation_violation_link_to_deleted(temp_storage):
    """Verify that deleting a file manually breaks integrity.
    
    V7.7: Integrity check happens at Memory initialization when loading existing data.
    The check verifies that all indexed files exist on disk.
    """
    # Create a single decision (no supersede to keep it active)
    memory = Memory(storage_path=temp_storage)
    res1 = memory.record_decision(title="D1", target="TargetArea", rationale="Rationale for first decision is long enough")
    fid1 = memory.get_decisions()[0]
    memory.close()  # Ensure data is committed to DB

    # Now manually delete the decision file
    os.remove(os.path.join(temp_storage, "semantic", fid1))

    # Restart should fail due to integrity issues (file missing from disk)
    with pytest.raises(IntegrityViolation) as excinfo:
        Memory(storage_path=temp_storage)

    # Check for appropriate error message
    error_msg = str(excinfo.value)
    assert "missing from disk" in error_msg or "Violation" in error_msg
    print("Isolation violation caught.")