import pytest
from unittest.mock import MagicMock
from agent_memory_core.api.memory import Memory
from agent_memory_core.stores.postgres import PostgresStore
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def test_memory_init_with_db_url(tmp_path):
    storage_path = str(tmp_path / "mem")
    # Using sqlite with sqlalchemy as a generic test for PostgresStore's SQLAlchemy logic
    db_url = "sqlite:///:memory:"
    
    # We need to mock Vector column because it's pgvector specific
    from unittest.mock import patch
    with patch('pgvector.sqlalchemy.Vector', MagicMock()):
        memory = Memory(storage_path=storage_path, db_url=db_url)
        assert isinstance(memory.vector, PostgresStore)
        assert isinstance(memory.semantic.meta, PostgresStore)

def test_postgres_store_upsert_logic():
    # Test only the SQLAlchemy logic using SQLite
    from unittest.mock import patch
    with patch('pgvector.sqlalchemy.Vector', MagicMock()):
        store = PostgresStore("sqlite:///:memory:")
        from datetime import datetime
        
        store.upsert(
            fid="test.md",
            target="test_target",
            status="active",
            kind="decision",
            timestamp=datetime.now()
        )
        
        active_fid = store.get_active_fid("test_target")
        assert active_fid == "test.md"

def test_postgres_store_list_all():
    from unittest.mock import patch
    with patch('pgvector.sqlalchemy.Vector', MagicMock()):
        store = PostgresStore("sqlite:///:memory:")
        from datetime import datetime
        
        store.upsert("f1.md", "t1", "active", "decision", datetime.now())
        store.upsert("f2.md", "t2", "superseded", "decision", datetime.now())
        
        all_meta = store.list_all()
        assert len(all_meta) == 2
        targets = [m['target'] for m in all_meta]
        assert "t1" in targets
        assert "t2" in targets

def test_postgres_store_episodic_logic():
    from unittest.mock import patch
    with patch('pgvector.sqlalchemy.Vector', MagicMock()):
        store = PostgresStore("sqlite:///:memory:")
        from agent_memory_core.core.schemas import MemoryEvent
        from datetime import datetime
        
        event = MemoryEvent(source="user", kind="error", content="hello", context={"a": 1})
        event_id = store.append(event)
        
        results = store.query(limit=1)
        assert len(results) == 1
        assert results[0]['content'] == "hello"
        assert results[0]['context']['a'] == 1
        assert results[0]['id'] == event_id

def test_postgres_store_link_logic():
    from unittest.mock import patch
    with patch('pgvector.sqlalchemy.Vector', MagicMock()):
        store = PostgresStore("sqlite:///:memory:")
        from agent_memory_core.core.schemas import MemoryEvent
        
        event = MemoryEvent(source="user", kind="error", content="hello")
        event_id = store.append(event)
        store.link_to_semantic(event_id, "decision_1.md")
        
        results = store.query(limit=1)
        assert results[0]['linked_id'] == "decision_1.md"
