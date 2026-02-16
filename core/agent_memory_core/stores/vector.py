import sqlite3
import json
import logging
from typing import List, Tuple, Optional, Any
import math
from datetime import datetime
from agent_memory_core.stores.interfaces import VectorProvider

logger = logging.getLogger("agent-memory-core.vector")

class VectorStore(VectorProvider):
    """
    Поисковый слой (Read-only для логики) для семантического поиска.
    """
    def __init__(self, db_path: str, compressor: Optional[Any] = None):
        self.db_path = db_path
        self.compressor = compressor
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_index (
                    decision_id TEXT PRIMARY KEY,
                    embedding BLOB,
                    text_preview TEXT,
                    metadata TEXT
                )
            """)
            conn.commit()

    def update_index(self, decision_id: str, embedding: List[float], text_preview: str, metadata: dict = None, namespace: str = "default"):
        """Обновляет или добавляет вектор в индекс."""
        if self.compressor:
            embedding_data = self.compressor.compress(embedding)
        else:
            embedding_data = json.dumps(embedding).encode()
            
        metadata_json = json.dumps(metadata or {})
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO vector_index (decision_id, embedding, text_preview, metadata) VALUES (?, ?, ?, ?)",
                (decision_id, embedding_data, text_preview, metadata_json)
            )
            conn.commit()

    def delete_from_index(self, decision_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM vector_index WHERE decision_id = ?", (decision_id,))
            conn.commit()

    def search(self, query_embedding: List[float], limit: int = 5,
               start_time: Optional[datetime] = None, 
               end_time: Optional[datetime] = None,
               namespace: str = "default") -> List[Tuple[str, float, str]]:
        """
        Выполняет поиск по сходству (cosine similarity).
        """
        results = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT decision_id, embedding, text_preview FROM vector_index")
            for row in cursor:
                doc_id, emb_data, preview = row
                
                if self.compressor:
                    doc_embedding = self.compressor.decompress(emb_data)
                else:
                    doc_embedding = json.loads(emb_data.decode())
                    
                score = self._cosine_similarity(query_embedding, doc_embedding)
                results.append((doc_id, score, preview))
        
        # Сортируем по убыванию сходства
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(b * b for b in v2))
        if not magnitude1 or not magnitude2:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)
