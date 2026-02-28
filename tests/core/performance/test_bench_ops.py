import pytest
import time
import uuid
import os
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import LedgermindConfig

@pytest.fixture
def memory_instance(tmp_path):
    storage_path = str(tmp_path / "bench_mem")
    # Check for pre-downloaded model in CI or local env
    model_path = os.environ.get("LEDGERMIND_MODEL_PATH")
    if not model_path:
        # Fallback to standard location relative to repo root
        standard_model = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf"))
        if os.path.exists(standard_model):
            model_path = standard_model

    config = LedgermindConfig(
        storage_path=storage_path,
        vector_model=model_path if model_path else "models/v5-small-text-matching-Q4_K_M.gguf",
        vector_workers=0,
        enable_git=False # Disable git for pure core performance benchmarking
    )
    return Memory(config=config)

def test_benchmark_record_decision(memory_instance, benchmark):
    def record():
        u = uuid.uuid4().hex
        memory_instance.record_decision(
            title=f"Performance Test {u}",
            target=f"perf_target_{u}",
            rationale="Benchmarking the overhead of a single decision recording without git."
        )
    
    benchmark(record)

def test_benchmark_search_decisions(memory_instance, benchmark):
    # Seed some data ONCE before the benchmark runs
    for i in range(10):
        memory_instance.record_decision(f"Decision {i}", f"target_{i}", f"Rationale for decision {i} with sufficient length for validation")
    
    def search():
        # Measure pure search speed
        memory_instance.search_decisions("Decision", limit=5)
    
    benchmark(search)
