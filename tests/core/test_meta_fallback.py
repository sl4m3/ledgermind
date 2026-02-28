import pytest
import sqlite3
from ledgermind.core.stores.semantic_store.meta import SemanticMetaStore
from datetime import datetime

@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_meta.db")
    s = SemanticMetaStore(db_path)
    # Populate with some data
    s.upsert("f1", "target1", "active", "decision", datetime.now(), title="Python Optimization", keywords="fast, efficient")
    s.upsert("f2", "target2", "active", "decision", datetime.now(), title="Java Performance", keywords="slow, memory")
    s.upsert("f3", "target3", "active", "decision", datetime.now(), title="Python Memory", keywords="garbage collection")
    return s

def test_fallback_search(store):
    # Force fallback by breaking FTS table
    try:
        store._conn.execute("DROP TABLE semantic_fts")
    except sqlite3.OperationalError:
        pass

    # Search for "Python"
    results = store.keyword_search("Python")
    titles = [r[1] for r in results] # Index 1 is title in raw tuples
    assert "Python Optimization" in titles
    assert "Python Memory" in titles
    assert "Java Performance" not in titles

    # Search for "Python Memory" (Two words)
    # With AND logic, should match "Python Memory" (has both)
    # "Python Optimization" has "Python" but not "Memory" -> Should NOT match
    results = store.keyword_search("Python Memory")
    titles = [r[1] for r in results]
    assert "Python Memory" in titles
    assert "Python Optimization" not in titles

    # Search for "fast"
    results = store.keyword_search("fast")
    titles = [r[1] for r in results]
    assert "Python Optimization" in titles
