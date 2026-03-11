import pytest
import concurrent.futures
import time
import os
import shutil
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.exceptions import ConflictError, InvariantViolation
from ledgermind.core.stores.semantic_store.integrity import IntegrityViolation

@pytest.fixture
def clean_storage(tmp_path):
    storage = str(tmp_path / "stress_mem")
    if os.path.exists(storage):
        shutil.rmtree(storage)
    return storage

def test_concurrent_writes(clean_storage):
    """
    Simulates high-load environment with multiple agents writing DIFFERENT targets.
    Expects all to succeed (eventual consistency/locking).
    """
    def worker(i):
        worker_mem = None
        try:
            worker_mem = Memory(storage_path=clean_storage)
            worker_mem.record_decision(f"Title {i}", f"target_{i}", f"Rationale {i}")
            return True
        except Exception as e:
            print(f"Worker {i} failed: {e}")
            return False
        finally:
            if worker_mem:
                worker_mem.close()

    num_workers = 5
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker, i) for i in range(num_workers)]
        results = [f.result() for f in futures]

    assert all(results), f"Not all workers succeeded: {results}"

def test_concurrent_conflict(clean_storage):
    """
    Simulates race condition where multiple agents try to write to the SAME target.
    Only one should succeed, others should fail with ConflictError or Timeout.
    """
    target = "shared_resource"

    def worker(i):
        worker_mem = None
        try:
            worker_mem = Memory(storage_path=clean_storage)
            # Use RADICALLY different content to ensure 0 similarity
            subjects = ["quantum physics", "medieval history", "culinary arts", "industrial mining"]
            subj = subjects[i % len(subjects)]
            worker_mem.record_decision(f"Title {i}", target, f"Rationale regarding {subj} with absolutely no overlap in semantic meaning.")
            return "success"
        except (ConflictError, InvariantViolation, IntegrityViolation):
            return "conflict"
        except Exception as e:
            msg = str(e)
            # Timeout is also a valid outcome (system protected itself)
            if "Timeout" in msg or "lock" in msg or "locked" in msg:
                return "timeout"
            # Generic string checks for safety
            if "CONFLICT" in msg or "Violation" in msg or "active decision" in msg:
                return "conflict"
            return f"error: {type(e).__name__} {msg}"
        finally:
            if worker_mem:
                worker_mem.close()

    num_workers = 2
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker, i) for i in range(num_workers)]
        results = [f.result() for f in futures]

    print(f"Full Results: {results}")

    success_count = results.count("success")
    conflict_count = results.count("conflict")
    timeout_count = results.count("timeout")

    print(f"Stats: Success={success_count}, Conflict={conflict_count}, Timeout={timeout_count}")

    # Only ONE should succeed if no timeouts/conflicts blocked everything
    assert success_count <= 1
    # Total must match
    assert success_count + conflict_count + timeout_count == num_workers
