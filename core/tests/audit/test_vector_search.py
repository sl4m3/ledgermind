import os
import pytest
import shutil
import tempfile
import numpy as np
from unittest.mock import MagicMock
from agent_memory_core.api.memory import Memory

@pytest.fixture
def temp_storage():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture
def mock_vector_store(temp_storage):
    from agent_memory_core.stores.vector import VectorStore
    vs = VectorStore(temp_storage, dimension=4)
    vs._model = MagicMock()
    def mock_encode(texts):
        # Create unique vectors for each text to test direction
        # doc1: [1,0,0,0], doc2: [0,1,0,0], etc.
        embs = []
        for t in texts:
            emb = np.zeros(4, dtype='float32')
            if "Short" in t or "12345" in t: emb[0] = 1.0
            elif "Medium" in t: emb[1] = 1.0
            else: emb[2] = 1.0
            embs.append(emb)
        return embs
    vs._model.encode = mock_encode
    
    import agent_memory_core.stores.vector
    agent_memory_core.stores.vector.EMBEDDING_AVAILABLE = True
    return vs

def test_vector_store_numpy_ops(mock_vector_store):
    """Test that VectorStore (NumPy) can add and search documents."""
    docs = [
        {"id": "doc1", "content": "Short"},      # length 5
        {"id": "doc2", "content": "Medium text"}, # length 11
        {"id": "doc3", "content": "Very long text content"} # length 21
    ]
    
    mock_vector_store.add_documents(docs)
    
    # Search for something that should be close to "Short"
    results = mock_vector_store.search("12345", limit=1)
    assert len(results) > 0
    assert results[0]["id"] == "doc1"
    assert results[0]["score"] > 0.9

def test_vector_store_persistence(temp_storage):
    """Test that NumPy vectors persist correctly to disk."""
    from agent_memory_core.stores.vector import VectorStore
    vs = VectorStore(temp_storage, dimension=4)
    vs._model = MagicMock()
    vs._model.encode = lambda texts: [np.array([1, 2, 3, 4], dtype='float32') for _ in texts]
    
    import agent_memory_core.stores.vector
    agent_memory_core.stores.vector.EMBEDDING_AVAILABLE = True
    
    vs.add_documents([{"id": "persist1", "content": "test content"}])
    vs.save()
    
    vs2 = VectorStore(temp_storage, dimension=4)
    vs2.load()
    assert len(vs2._doc_ids) == 1
    assert vs2._doc_ids[0] == "persist1"
    assert vs2._vectors.shape == (1, 4)

def test_memory_vector_search_fallback(temp_storage, monkeypatch):
    """Test that search falls back to keyword search if embedding model is missing."""
    import agent_memory_core.stores.vector
    monkeypatch.setattr(agent_memory_core.stores.vector, "EMBEDDING_AVAILABLE", False)
    
    mem = Memory(storage_path=temp_storage)
    mem.record_decision(
        title="Keyword Test",
        target="test",
        rationale="Fallback test"
    )
    
    results = mem.search_decisions("Keyword", limit=1)
    assert len(results) > 0
    assert results[0]["title"] == "Keyword Test"
    assert results[0]["score"] == 0.5
