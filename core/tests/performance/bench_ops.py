import pytest
import time
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import EmbeddingProvider

class MockEmbeddingProvider(EmbeddingProvider):
    def get_embedding(self, text: str):
        return [0.1] * 1536

@pytest.fixture
def memory_instance(tmp_path):
    storage_path = str(tmp_path / "bench_mem")
    return Memory(storage_path=storage_path, embedding_provider=MockEmbeddingProvider())

def test_benchmark_record_decision(memory_instance, benchmark):
    import uuid
    def record():
        memory_instance.record_decision(
            title="Performance Test",
            target=f"perf_target_{uuid.uuid4().hex}",
            rationale="Benchmarking the overhead of a single decision recording including git and sqlite."
        )
    
    benchmark(record)

def test_benchmark_search_decisions(memory_instance, benchmark):
    # Seed some data
    for i in range(10):
        memory_instance.record_decision(f"Decision {i}", f"target_{i}", f"Rationale for decision {i}")
    
    def search():
        memory_instance.search_decisions("finding something", limit=5)
    
    benchmark(search)
