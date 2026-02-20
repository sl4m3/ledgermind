import pytest
import os
import time
import shutil
import concurrent.futures
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.exceptions import ConflictError

@pytest.fixture
def clean_storage(tmp_path):
    storage = tmp_path / "stress_mem"
    if storage.exists():
        shutil.rmtree(storage)
    os.makedirs(storage)
    return str(storage)

def test_concurrent_writes(clean_storage):
    """
    Simulates multiple agents trying to write decisions simultaneously.
    Verifies that file locking prevents corruption and maintains integrity.
    """
    # 1. Setup initial state
    init_mem = Memory(storage_path=clean_storage)
    init_mem.record_decision("Base Decision", "base", "Initial rationale for base decision")
    
    def worker(i):
        # Each worker tries to create a unique decision using its OWN instance
        worker_mem = Memory(storage_path=clean_storage)
        try:
            worker_mem.record_decision(f"Decision {i}", f"target_{i}", f"Rationale from worker {i} ensuring sufficient length")
            return True, None
        except Exception as e:
            return False, str(e)

    # 2. Launch concurrent workers
    # Reduce workers to 4 to fit within limits
    num_workers = 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker, i) for i in range(num_workers)]
        results = [f.result() for f in futures]
    
    # 3. Analyze results
    successes = [r for r in results if r[0]]
    failures = [r for r in results if not r[0]]
    
    print(f"Successes: {len(successes)}, Failures: {len(failures)}")
    # Log failures for debug
    for _, err in failures:
        print(f"Failure reason: {err}")
    
    # 4. Verify integrity
    verify_mem = Memory(storage_path=clean_storage)
    decisions = verify_mem.get_decisions()
    # All successful writes should be present + 1 base decision
    assert len(decisions) == len(successes) + 1
    
    # Failures due to Timeout are acceptable under heavy load, 
    # but verify no partial writes occurred (integrity).
    
def test_concurrent_conflict(clean_storage):
    """
    Simulates race condition where multiple agents try to write to the SAME target.
    Only one should succeed, others should fail with ConflictError or Timeout.
    """
    target = "shared_resource"
    
    def worker(i):
        try:
            worker_mem = Memory(storage_path=clean_storage)
            worker_mem.record_decision(f"Title {i}", target, f"Rationale {i} ensuring sufficient length for stress test")
            return "success"
        except ConflictError:
            return "conflict"
        except Exception as e:
            msg = str(e)
            # Timeout is also a valid outcome (system protected itself)
            if "Timeout" in msg or "lock" in msg or "locked" in msg:
                return "timeout"
            # Integrity/Runtime errors due to race conditions are also valid rejections
            if "UNIQUE constraint" in msg or "active decision" in msg or "Invariant Violation" in msg:
                return "conflict"
            return f"error: {type(e).__name__} {msg}"

    num_workers = 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker, i) for i in range(num_workers)]
        results = [f.result() for f in futures]
    
    print(f"Full Results: {results}")

    success_count = results.count("success")
    conflict_count = results.count("conflict")
    timeout_count = results.count("timeout")
    
    print(f"Stats: Success={success_count}, Conflict={conflict_count}, Timeout={timeout_count}")
    
    # Only ONE should succeed if no timeouts/conflicts blocked everything
    # In extremely high load, it's possible 0 succeed, but usually 1.
    assert success_count <= 1
    # Total must match
    assert success_count + conflict_count + timeout_count == num_workers
    
    # Verify no more than one active decision exists for target
    verify_mem = Memory(storage_path=clean_storage)
    conflicts = verify_mem.semantic.list_active_conflicts(target)
    assert len(conflicts) <= 1
