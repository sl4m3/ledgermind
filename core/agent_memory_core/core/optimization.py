import hashlib
import json
import sqlite3
import logging
import zstandard as zstd
from typing import List, Optional, Union
from agent_memory_core.core.schemas import EmbeddingProvider

logger = logging.getLogger("agent-memory-core.optimization")

class EmbeddingCache:
    """Persistent cache for embeddings to reduce API costs."""
    def __init__(self, cache_db_path: str):
        self.db_path = cache_db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS emb_cache (text_hash TEXT PRIMARY KEY, embedding BLOB)")

    def get(self, text: str) -> Optional[List[float]]:
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT embedding FROM emb_cache WHERE text_hash = ?", (text_hash,)).fetchone()
            if row:
                return json.loads(row[0])
        return None

    def set(self, text: str, embedding: List[float]):
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO emb_cache (text_hash, embedding) VALUES (?, ?)", 
                         (text_hash, json.dumps(embedding)))

class VectorCompressor:
    """Handles compression of high-dimensional vectors."""
    def __init__(self, level: int = 3):
        self.cctx = zstd.ZstdCompressor(level=level)
        self.dctx = zstd.ZstdDecompressor()

    def compress(self, embedding: List[float]) -> bytes:
        data = json.dumps(embedding).encode()
        return self.cctx.compress(data)

    def decompress(self, compressed_data: bytes) -> List[float]:
        decompressed = self.dctx.decompress(compressed_data)
        return json.loads(decompressed.decode())

class CachingEmbeddingProvider(EmbeddingProvider):
    """Wrapper that adds caching to any EmbeddingProvider."""
    def __init__(self, base_provider: EmbeddingProvider, cache: EmbeddingCache):
        self.base = base_provider
        self.cache = cache

    def get_embedding(self, text: str) -> List[float]:
        cached = self.cache.get(text)
        if cached:
            return cached
        
        emb = self.base.get_embedding(text)
        self.cache.set(text, emb)
        return emb
