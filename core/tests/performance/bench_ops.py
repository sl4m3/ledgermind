import pytest
import time
import uuid
from agent_memory_core.api.memory import Memory

@pytest.fixture
def memory_instance(tmp_path):
    storage_path = str(tmp_path / "bench_mem")
    return Memory(storage_path=storage_path)

def test_benchmark_record_decision(memory_instance, benchmark):
    def record():
        u = uuid.uuid4().hex
        memory_instance.record_decision(
            title=f"Performance Test {u}",
            target=f"perf_target_{u}",
            rationale="Benchmarking the overhead of a single decision recording including git and sqlite."
        )
    
    benchmark(record)

def test_benchmark_search_decisions(memory_instance, benchmark):
    # Seed some data
    for i in range(10):
        memory_instance.record_decision(f"Decision {i}", f"target_{i}", f"Rationale for decision {i} with sufficient length for validation")
    
    def search():
        memory_instance.search_decisions("finding", limit=5)
    
    benchmark(search)
