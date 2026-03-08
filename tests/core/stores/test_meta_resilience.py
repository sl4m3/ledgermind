import pytest
import sqlite3
from ledgermind.core.stores.semantic_store.meta import SemanticMetaStore

@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "resilience.db")
    return SemanticMetaStore(db_path)

def test_reentrant_batch_update(store):
    """Verify that batch_update supports re-entry without SQLite errors."""
    with store.batch_update():
        # Inner call should detect it is already in transaction and not fail
        with store.batch_update():
            # Perform some operation
            store.set_config("inner", "active")
        
        store.set_config("outer", "done")
    
    assert store.get_config("inner") == "active"
    assert store.get_config("outer") == "done"

def test_robust_like_fallback_case_insensitivity(store):
    """Verify that keyword_search fallback handles case-insensitivity for ASCII."""
    # 1. Seed data with mixed case
    from datetime import datetime
    store.upsert(
        fid="case_test.md", target="core/test", title="Database Optimization",
        content="Technical details", status="active", kind="decision",
        timestamp=datetime.now()
    )
    
    # 2. Force fallback by dropping FTS5
    store._conn.execute("DROP TABLE semantic_fts")
    
    # 3. Search with different case
    results = store.keyword_search("optimization")
    
    assert len(results) > 0
    assert "Database Optimization" in results[0]['title']
