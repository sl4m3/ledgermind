import pytest
import sqlite3
from datetime import datetime
from ledgermind.core.stores.semantic_store.meta import SemanticMetaStore

@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_meta.db")
    return SemanticMetaStore(db_path)

def test_fallback_search_logic(store):
    """Verify that search works even if FTS5 table is missing (using LIKE fallback)."""
    # 1. Seed data
    store.upsert(
        fid="python_opt.md", target="core/python", title="Python Optimization",
        content="Fast execution techniques for Python", status="active", kind="decision",
        timestamp=datetime.now(), context_json="{}"
    )
    store.upsert(
        fid="java_perf.md", target="core/java", title="Java Performance",
        content="Garbage collection tuning", status="active", kind="decision",
        timestamp=datetime.now(), context_json="{}"
    )

    # 2. Break FTS table to force fallback
    store._conn.execute("DROP TABLE semantic_fts")
    
    # 3. Search for "Python"
    results = store.keyword_search("Python")
    assert len(results) > 0
    # Index 1 is title in the raw tuple return
    assert any("Python" in r['title'] for r in results)
    assert not any("Java" in r['title'] for r in results)

    # 4. Search for "fast" (should match content field via LIKE)
    results_fast = store.keyword_search("fast")
    assert len(results_fast) > 0
    assert "Python Optimization" in results_fast[0]['title']
