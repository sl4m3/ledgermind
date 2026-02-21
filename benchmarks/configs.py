import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import TrustBoundary

class BenchmarkConfig:
    """Interface for system configuration during benchmarks."""
    def __init__(self, name: str):
        self.name = name
        self.temp_dir = tempfile.mkdtemp(prefix=f"lm_bench_{name}_")
        self.memory = None

    def setup(self):
        """Initializes the memory system in a specific mode."""
        pass

    def teardown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def search(self, query: str, limit: int = 5) -> List[str]:
        """Wrapper for search operation returning only IDs."""
        if not self.memory: return []
        results = self.memory.search_decisions(query, limit=limit, mode="balanced")
        return [r['id'] for r in results]

class FullLedgerMind(BenchmarkConfig):
    """Full version with vector search and hybrid ranking."""
    def setup(self):
        self.memory = Memory(storage_path=self.temp_dir, vector_workers=1)

class KeywordOnlyLedgerMind(BenchmarkConfig):
    """LedgerMind with vector search disabled via workers=0."""
    def setup(self):
        # We also force disable embedding availability if possible or ignore it in search
        import ledgermind.core.stores.vector
        ledgermind.core.stores.vector.EMBEDDING_AVAILABLE = False
        self.memory = Memory(storage_path=self.temp_dir, vector_workers=0)

class BaselineFlat(BenchmarkConfig):
    """Simplified version without conflict detection/supersede logic."""
    def setup(self):
        # We manually bypass the complex Logic in record_decision by using process_event
        self.memory = Memory(storage_path=self.temp_dir, vector_workers=0)
    
    def record_direct(self, title: str, target: str, rationale: str):
        """Bypasses ConflictEngine for baseline comparison."""
        from ledgermind.core.core.schemas import KIND_DECISION
        ctx = {"title": title, "target": target, "status": "active", "rationale": rationale}
        self.memory.process_event(source="agent", kind=KIND_DECISION, content=title, context=ctx)

class BaselineSQL(BenchmarkConfig):
    """Direct SQLite search (Keyword-like) for simplest baseline."""
    def setup(self):
        self.memory = Memory(storage_path=self.temp_dir, vector_workers=0)
    
    def search(self, query: str, limit: int = 5) -> List[str]:
        # Direct access to the internal sqlite metadata store
        results = self.memory.semantic.meta.keyword_search(query, limit=limit)
        return [r['fid'] for r in results]

def get_config_factory(mode: str) -> BenchmarkConfig:
    if mode == "full": return FullLedgerMind("Full")
    if mode == "keyword": return KeywordOnlyLedgerMind("Keyword")
    if mode == "baseline_flat": return BaselineFlat("BaselineFlat")
    if mode == "baseline_sql": return BaselineSQL("BaselineSQL")
    raise ValueError(f"Unknown benchmark mode: {mode}")
