import os
import shutil
import pytest
import threading
import time
from unittest.mock import MagicMock
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.exceptions import ConflictError

@pytest.fixture
def temp_memory_path(tmp_path):
    path = tmp_path / "memory"
    os.makedirs(path, exist_ok=True)
    return str(path)

def test_transaction_atomicity_rollback(temp_memory_path):
    """Ensures rollback of SQLite and Filesystem on Git failure."""
    memory = Memory(storage_path=temp_memory_path)
    target = "Atomicity-Test-Target"
    
    memory.record_decision(
        title="Initial State",
        target=target,
        rationale="Base version for atomicity test."
    )
    
    initial_fid = memory.get_decisions()[0]
    
    # Force Git failure by direct override on 'run'
    original_run = memory.semantic.audit.run
    def failing_run(*args, **kwargs):
        raise RuntimeError("Simulated Git Failure")
    
    memory.semantic.audit.run = failing_run
    
    try:
        with pytest.raises(RuntimeError, match="Simulated Git Failure"):
            memory.supersede_decision(
                title="Failed State",
                target=target,
                rationale="This should trigger a full rollback.",
                old_decision_ids=[initial_fid]
            )
            
        # Verify Rollback: Only 1 active record in SQLite and 1 file on disk
        memory.semantic.sync_meta_index()
        active = [m for m in memory.semantic.meta.list_all() if m['status'] == 'active']
        assert len(active) == 1
        assert active[0]['fid'] == initial_fid
        
        files = [f for f in os.listdir(os.path.join(temp_memory_path, "semantic")) if f.startswith("decision_")]
        assert len(files) == 1
    finally:
        memory.semantic.audit.run = original_run

def test_concurrency_locking_parallel_evolution(temp_memory_path):
    """Ensures thread-safety and ConflictEngine blocking during parallel evolution."""
    memory = Memory(storage_path=temp_memory_path)
    target = "Concurrency-Test-Target"
    
    initial_res = memory.record_decision(
        title="Evolution 0",
        target=target,
        rationale="Starting point."
    )
    initial_id = initial_res.metadata["file_id"]
    
    results, errors = [], []
    os.environ["LEDGERMIND_TEST_DELAY"] = "0.2"
    
    def worker(worker_id):
        # Using the SHARED memory instance to test threading.RLock
        try:
            res = memory.supersede_decision(
                title=f"Evolution by Worker {worker_id}",
                target=target,
                rationale=f"Worker {worker_id} is trying to evolve the knowledge.",
                old_decision_ids=[initial_id]
            )
            results.append(res.metadata["file_id"])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    del os.environ["LEDGERMIND_TEST_DELAY"]
    
    # 1 success, others fail due to deactivation or race condition protection
    assert len(results) == 1
    assert len(errors) == 4

def test_namespace_isolation(temp_memory_path):
    """Ensures targets are isolated between namespaces."""
    memory = Memory(storage_path=temp_memory_path)
    target = "Cross-Namespace-Target"
    
    memory.record_decision(title="Prod Config", target=target, rationale="Prod rules.", namespace="prod")
    memory.record_decision(title="Dev Config", target=target, rationale="Dev rules.", namespace="dev")
    
    assert len(memory.search_decisions(target, namespace="prod")) == 1
    assert len(memory.search_decisions(target, namespace="dev")) == 1
    assert len(memory.search_decisions(target, namespace="default")) == 0

def test_hard_purge_gdpr(temp_memory_path):
    """Ensures forget() removes record from disk and metadata."""
    memory = Memory(storage_path=temp_memory_path)
    res = memory.record_decision(title="Secret", target="Sensitive", rationale="Sensitive info.")
    fid = res.metadata["file_id"]
    
    memory.forget(fid)
    assert fid not in memory.get_decisions()
    assert not os.path.exists(os.path.join(temp_memory_path, "semantic", fid))
