"""Модель эмбеддингов с умным кэшированием."""

from typing import List, Optional, Tuple, Any
import numpy as np
from dataclasses import dataclass
from collections import OrderedDict
import hashlib
import time
import logging

logger = logging.getLogger("ledgermind.merging.embedding")

@dataclass
class EmbeddingCache:
    """LRU кэш с TTL."""
    max_size: int = 10000
    ttl_seconds: int = 3600

    def __post_init__(self):
        self._cache: OrderedDict[str, Tuple[List[float], float]] = OrderedDict()

    def get(self, key: str) -> Optional[List[float]]:
        if key in self._cache:
            embedding, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                self._cache.move_to_end(key)
                return embedding
            else:
                del self._cache[key]
        return None

    def set(self, key: str, embedding: List[float]) -> None:
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (embedding, time.time())


class JinaEmbeddingModel:
    """Обёртка для Jina v5 small 4bit."""

    def __init__(self, model_name: str = "jina-v5-small-4bit", cache_size: int = 10000, model_instance: Any = None):
        self.model_name = model_name
        self.cache = EmbeddingCache(max_size=cache_size)
        # Use provided instance or load a new one
        self._model = model_instance if model_instance is not None else self._load_model()

    def _load_model(self):
        """Загрузка модели (ленивая)."""
        try:
            # TODO: интегрировать с ledgermind.init
            from ledgermind.models.jina import JinaEncoder
            return JinaEncoder(model_name=self.model_name)
        except ImportError as e:
            logger.warning(f"Не удалось загрузить Jina модель: {e}. Используем fallback.")
            return None

    def _text_hash(self, text: str) -> str:
        """Хэш для кэширования."""
        normalized = self._normalize_text(text)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]

    def _normalize_text(self, text: str) -> str:
        """Нормализация для кэширования."""
        import re
        return re.sub(r'\s+', ' ', text.strip()).lower()

    def encode(self, texts: List[str]) -> np.ndarray:
        """Батч-кодирование с кэшированием."""
        if not texts:
            return np.array([])

        embeddings = []
        texts_to_encode = []
        text_indices = []

        # Проверка кэша
        for i, text in enumerate(texts):
            if not text.strip():
                embeddings.append(np.zeros(768))
                continue

            text_hash = self._text_hash(text)
            cached = self.cache.get(text_hash)
            if cached is not None:
                embeddings.append(np.array(cached))
            else:
                texts_to_encode.append(text)
                text_indices.append(i)
                embeddings.append(None)

        # Кодирование новых текстов
        if texts_to_encode and self._model is not None:
            try:
                new_embeddings = self._model.encode(texts_to_encode)
                for text, emb in zip(texts_to_encode, new_embeddings):
                    text_hash = self._text_hash(text)
                    self.cache.set(text_hash, emb.tolist())

                for idx, emb in zip(text_indices, new_embeddings):
                    embeddings[idx] = emb
            except Exception as e:
                logger.error(f"Ошибка кодирования: {e}")
                # Fallback to hash-based pseudo-embedding
                for idx, text in zip(text_indices, texts_to_encode):
                    embeddings[idx] = self._get_hash_embedding(text)
        elif texts_to_encode:
            # Fallback to hash-based pseudo-embedding if model not loaded
            for idx, text in zip(text_indices, texts_to_encode):
                embeddings[idx] = self._get_hash_embedding(text)

        return np.array(embeddings)

    def _get_hash_embedding(self, text: str) -> np.ndarray:
        """Генерирует детерминированный псевдо-эмбеддинг на основе хеша текста."""
        # Чтобы векторы были более ортогональными, генерируем их частями с разными солями
        vec = np.zeros(768, dtype=np.float32)
        for i in range(12): # 12 * 64 байта = 768 байт
            h = hashlib.blake2b(text.encode('utf-8'), salt=str(i).encode(), digest_size=64).digest()
            vec[i*64:(i+1)*64] = np.frombuffer(h, dtype=np.uint8).astype(np.float32) / 255.0
        
        # Центрируем и нормализуем вектор для честного косинусного сходства
        vec = vec - 0.5
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    @staticmethod
    def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Косинусное сходство [0, 1] (предполагая положительные или нормализованные векторы)."""
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        # Raw cosine similarity: (A dot B) / (|A|*|B|)
        cos_sim = np.dot(emb1, emb2) / (norm1 * norm2)
        
        # Clip to [0, 1] range as most embedding models produce positive-leaning cosine for similar texts.
        # This prevents floating point errors from going out of bounds.
        return float(max(0.0, min(1.0, cos_sim)))
