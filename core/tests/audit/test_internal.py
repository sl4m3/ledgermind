import pytest
import asyncio
from unittest.mock import MagicMock
from agent_memory_core.core.events import MemoryEventEmitter
from agent_memory_core.core.optimization import EmbeddingCache, CachingEmbeddingProvider, VectorCompressor
from agent_memory_core.core.telemetry import update_decision_metrics

@pytest.mark.asyncio
async def test_event_emitter():
    emitter = MemoryEventEmitter()
    received = []
    
    async def callback(event_type, data):
        received.append((event_type, data))
        
    emitter.subscribe(callback)
    await emitter.emit("test_event", {"payload": 123})
    
    assert len(received) == 1
    assert received[0][0] == "test_event"
    assert received[0][1]["payload"] == 123

def test_vector_compressor():
    compressor = VectorCompressor()
    original_vec = [0.1, 0.2, 0.3, 0.4, 0.5]
    
    compressed = compressor.compress(original_vec)
    assert isinstance(compressed, bytes)
    
    decompressed = compressor.decompress(compressed)
    assert decompressed == original_vec

def test_embedding_cache(tmp_path):
    cache_db = str(tmp_path / "cache.db")
    cache = EmbeddingCache(cache_db)
    
    text = "some text to embed"
    vec = [1.0, 2.0, 3.0]
    
    # 1. Set
    cache.set(text, vec)
    
    # 2. Get
    res = cache.get(text)
    assert res == vec
    
    # 3. Cache Miss
    assert cache.get("other text") is None

def test_caching_provider(tmp_path):
    cache = EmbeddingCache(str(tmp_path / "cache2.db"))
    base_provider = MagicMock()
    base_provider.get_embedding.return_value = [0.9, 0.8]
    
    caching_provider = CachingEmbeddingProvider(base_provider, cache)
    
    # First call - goes to base
    res1 = caching_provider.get_embedding("hello")
    assert res1 == [0.9, 0.8]
    assert base_provider.get_embedding.call_count == 1
    
    # Second call - goes to cache
    res2 = caching_provider.get_embedding("hello")
    assert res2 == [0.9, 0.8]
    assert base_provider.get_embedding.call_count == 1
