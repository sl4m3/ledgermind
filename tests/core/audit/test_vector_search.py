import os
import pytest
import shutil
import tempfile
import numpy as np
from unittest.mock import MagicMock
from ledgermind.core.api.memory import Memory

@pytest.fixture
def temp_storage():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture
def mock_vector_store(temp_storage):
    from ledgermind.core.stores.vector import VectorStore
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
    
    import ledgermind.core.stores.vector
    ledgermind.core.stores.vector.EMBEDDING_AVAILABLE = True
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
    results = mock_vector_store.search("Short", limit=1)
    assert len(results) > 0
    assert results[0]["id"] == "doc1"
    # Use a more realistic threshold for real embeddings
    assert results[0]["score"] > 0.5

def test_vector_store_persistence(temp_storage):
    """Test that NumPy vectors persist correctly to disk."""
    from ledgermind.core.stores.vector import VectorStore, _MODEL_CACHE
    # Clear cache to avoid dimension mismatch from previous tests
    _MODEL_CACHE.clear()
    
    vs = VectorStore(temp_storage, dimension=4)
    # Mocking the model to return 4-dim vectors
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 4
    mock_model.encode.side_effect = lambda texts: [np.array([0.1, 0.2, 0.3, 0.4], dtype='float32') for _ in texts]
    
    # Inject mock into cache
    _MODEL_CACHE[vs.model_name] = mock_model
    
    import ledgermind.core.stores.vector
    ledgermind.core.stores.vector.EMBEDDING_AVAILABLE = True

    vs.add_documents([{"id": "persist1", "content": "test content"}])
    vs.save()

    vs2 = VectorStore(temp_storage, dimension=4)
    vs2.load()
    assert len(vs2._doc_ids) == 1
    assert vs2._doc_ids[0] == "persist1"
    assert vs2._vectors.shape == (1, 4)
    # Clean up
    _MODEL_CACHE.clear()
def test_memory_vector_search_fallback(temp_storage, monkeypatch):
    """Test that search falls back to keyword search if embedding model is missing."""
    import ledgermind.core.stores.vector
    monkeypatch.setattr(ledgermind.core.stores.vector, "EMBEDDING_AVAILABLE", False)
    
    mem = Memory(storage_path=temp_storage)
    mem.record_decision(
        title="Keyword Test",
        target="test",
        rationale="Fallback test"
    )
    
    results = mem.search_decisions("Keyword", limit=1)
    assert len(results) > 0
    assert results[0]["title"] == "Keyword Test"
    assert results[0]["score"] >= 0.5
    
