"""Embedding provider contract over the Local technical backend."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Sequence

from ledgermind_inference.embedding_provider import (
    EmbeddingBatch,
    EmbeddingBatchRequest,
    EmbeddingBatchTooLargeError,
    EmbeddingCacheSchemaError,
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingModelError,
    EmbeddingNonFiniteError,
    EmbeddingProvider,
    EmbeddingRequestError,
    EmbeddingTextTooLargeError,
    EmbeddingVectorCache,
    VectorizerFactory,
)


class PersistentEmbeddingCache(EmbeddingVectorCache):
    """SQLite-backed immutable embedding cache owned by Local."""

    def __init__(self, database_path: str | Path) -> None:
        super().__init__()
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'embedding_vector_cache'"
            ).fetchone()
            if table is None:
                raise EmbeddingCacheSchemaError(
                    "embedding_vector_cache is not owned by the runtime; "
                    "apply Local migrations through 0010 before opening the cache"
                )
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(embedding_vector_cache)"
                ).fetchall()
            }
            required = {
                "cache_key",
                "profile_fingerprint",
                "cache_namespace",
                "content_digest",
                "dimensions",
                "vector_json",
                "created_at",
            }
            missing = sorted(required - columns)
            if missing:
                raise EmbeddingCacheSchemaError(
                    "embedding_vector_cache schema is incomplete: "
                    + ", ".join(missing)
                )
            index = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' "
                "AND name = 'ix_embedding_vector_cache_profile'"
            ).fetchone()
            if index is None:
                raise EmbeddingCacheSchemaError(
                    "embedding_vector_cache profile index is missing from migration history"
                )

    def get(self, key: str) -> tuple[float, ...] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT vector_json FROM embedding_vector_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                self.misses += 1
                return None
            try:
                values = json.loads(str(row[0]))
                vector = tuple(float(value) for value in values)
                if not vector or not all(math.isfinite(value) for value in vector):
                    raise ValueError("invalid cached vector")
            except (TypeError, ValueError, json.JSONDecodeError):
                connection.execute(
                    "DELETE FROM embedding_vector_cache WHERE cache_key = ?",
                    (key,),
                )
                self.misses += 1
                return None
            self.hits += 1
            return vector

    def put(
        self,
        key: str,
        vector: Sequence[float],
        *,
        profile_fingerprint: str = "",
        namespace: str = "",
        content_digest: str | None = None,
    ) -> None:
        values = tuple(float(value) for value in vector)
        if not values or not all(math.isfinite(value) for value in values):
            raise ValueError("embedding cache vectors must be finite and non-empty")
        payload = json.dumps(list(values), allow_nan=False, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO embedding_vector_cache (
                    cache_key, profile_fingerprint, cache_namespace,
                    content_digest, dimensions, vector_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    profile_fingerprint = excluded.profile_fingerprint,
                    cache_namespace = excluded.cache_namespace,
                    content_digest = excluded.content_digest,
                    dimensions = excluded.dimensions,
                    vector_json = excluded.vector_json,
                    created_at = excluded.created_at
                """,
                (
                    key,
                    profile_fingerprint,
                    namespace,
                    content_digest or key,
                    len(values),
                    payload,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def clear(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM embedding_vector_cache")
            self.hits = 0
            self.misses = 0

    @property
    def size(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM embedding_vector_cache"
            ).fetchone()
            return int(row[0]) if row is not None else 0


EmbeddingCache = EmbeddingVectorCache

__all__ = [
    "EmbeddingBatch",
    "EmbeddingBatchRequest",
    "EmbeddingBatchTooLargeError",
    "EmbeddingCache",
    "EmbeddingCacheSchemaError",
    "EmbeddingDimensionMismatchError",
    "EmbeddingError",
    "EmbeddingModelError",
    "EmbeddingNonFiniteError",
    "EmbeddingProvider",
    "EmbeddingRequestError",
    "EmbeddingTextTooLargeError",
    "EmbeddingVectorCache",
    "PersistentEmbeddingCache",
    "VectorizerFactory",
]
