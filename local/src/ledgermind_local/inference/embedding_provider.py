"""Embedding provider contract over the Local technical backend."""

from __future__ import annotations

import math
import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..embedding_purpose import EmbeddingPurpose, validate_embedding_purpose
from .cancellation import CancellationToken
from .profiles import (
    EmbeddingProfileIdentity,
    EmbeddingProfileReadiness,
    InferenceProfile,
)
from .vectorizer import EmbeddingRole, Vectorizer
from .provider_telemetry import record_task

VectorizerFactory = Callable[[], Vectorizer]


class EmbeddingBatch(BaseModel):
    """Typed embedding result with model identity metadata and no content coupling."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    vectors: tuple[tuple[float, ...], ...]
    model: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    dimensions: int = Field(gt=0)
    purpose: str = Field(min_length=1)
    role: EmbeddingRole | None = None
    renderer_version: str | None = Field(default=None, min_length=1)


@dataclass(frozen=True, slots=True)
class EmbeddingBatchRequest:
    """One semantic-free member of a generic embedding batch."""

    texts: tuple[str, ...]
    profile: InferenceProfile
    purpose: EmbeddingPurpose
    dimensions: int | None = None
    cache_keys: tuple[str, ...] | None = None
    cache_namespace: str = ""
    profile_fingerprint: str | None = None
    config_fingerprint: str | None = None
    privacy_class: str = "default"
    deadline: str | None = None
    role: EmbeddingRole | None = None
    renderer_version: str | None = None


class EmbeddingVectorCache:
    """Small content-addressed cache shared by compatible embedding tasks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._vectors: dict[str, tuple[float, ...]] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def digest(
        *,
        profile_fingerprint: str,
        namespace: str,
        content: str,
        role: EmbeddingRole | None = None,
        renderer_version: str | None = None,
    ) -> str:
        material = "\x1f".join(
            (
                profile_fingerprint,
                namespace,
                renderer_version or "plain",
                role or "plain",
                content,
            )
        )
        return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()

    def get(self, key: str) -> tuple[float, ...] | None:
        with self._lock:
            value = self._vectors.get(key)
            if value is None:
                self.misses += 1
                return None
            self.hits += 1
            return value

    def put(
        self,
        key: str,
        vector: Sequence[float],
        *,
        profile_fingerprint: str = "",
        namespace: str = "",
        content_digest: str | None = None,
    ) -> None:
        del profile_fingerprint, namespace, content_digest
        with self._lock:
            self._vectors[key] = tuple(float(value) for value in vector)

    def clear(self) -> None:
        with self._lock:
            self._vectors.clear()
            self.hits = 0
            self.misses = 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._vectors)


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


# The shorter name is useful to callers that treat this as a Local-owned
# embedding cache rather than a vector implementation detail.
EmbeddingCache = EmbeddingVectorCache


class EmbeddingError(RuntimeError):
    """Base embedding failure with a safe, structured code."""

    code = "embedding_error"


class EmbeddingRequestError(EmbeddingError):
    code = "embedding_request_error"


class EmbeddingBatchTooLargeError(EmbeddingError):
    code = "embedding_batch_too_large"


class EmbeddingTextTooLargeError(EmbeddingError):
    code = "embedding_text_too_large"


class EmbeddingNonFiniteError(EmbeddingError):
    code = "embedding_non_finite"


class EmbeddingDimensionMismatchError(EmbeddingError):
    code = "embedding_dimension_mismatch"


class EmbeddingModelError(EmbeddingError):
    code = "embedding_model_error"


class EmbeddingCacheSchemaError(EmbeddingError):
    """The Local migration-owned persistent cache schema is unavailable."""

    code = "embedding_cache_schema_error"


class EmbeddingProvider:
    """Local embedding boundary wrapping the existing vectorizer, never copying it."""

    def __init__(
        self,
        *,
        vectorizer_factory: VectorizerFactory,
        max_texts: int = 64,
        max_text_chars: int = 8_000,
        identity_config: Mapping[str, object] | None = None,
        cache: EmbeddingVectorCache | None = None,
    ) -> None:
        if max_texts < 1:
            raise ValueError("max_texts must be positive")
        if max_text_chars < 1:
            raise ValueError("max_text_chars must be positive")
        self._vectorizer_factory = vectorizer_factory
        self.max_texts = max_texts
        self.max_text_chars = max_text_chars
        self._identity_config = dict(identity_config or {})
        self.cache = cache

    def describe_profile(self, profile: InferenceProfile) -> EmbeddingProfileIdentity:
        """Resolve opaque embedding identity without sending any text."""

        vectorizer = self._vectorizer_factory()
        try:
            return self._profile_identity(
                profile,
                vectorizer,
                self._vectorizer_dimension(vectorizer),
            )
        finally:
            close = getattr(vectorizer, "close", None)
            if callable(close):
                close()

    # Explicit alias for callers that name the contract rather than the action.
    embedding_profile_identity = describe_profile

    def readiness(self, profile: InferenceProfile) -> EmbeddingProfileReadiness:
        """Return secret-free profile readiness and identity metadata."""

        try:
            identity = self.describe_profile(profile)
        except Exception as exc:  # noqa: BLE001 - readiness must remain observable
            code = getattr(exc, "code", None)
            if not isinstance(code, str) or not code:
                code = "embedding_profile_unavailable"
            return EmbeddingProfileReadiness(
                profile_id=profile.profile_id,
                ready=False,
                error_code=code,
            )
        if identity.dimensions is None:
            return EmbeddingProfileReadiness(
                profile_id=profile.profile_id,
                ready=False,
                identity=identity,
                error_code="embedding_dimensions_unknown",
            )
        return EmbeddingProfileReadiness(
            profile_id=profile.profile_id,
            ready=True,
            identity=identity,
        )

    def embed(
        self,
        texts: Sequence[str],
        profile: InferenceProfile,
        purpose: EmbeddingPurpose,
        *,
        cancellation_token: CancellationToken | None = None,
        role: EmbeddingRole | None = None,
        renderer_version: str | None = None,
    ) -> EmbeddingBatch:
        """Embed ``texts`` through the local backend and validate the batch."""
        return self.embed_many(
            (
                EmbeddingBatchRequest(
                    texts=tuple(texts),
                    profile=profile,
                    purpose=purpose,
                    role=role,
                    renderer_version=renderer_version,
                ),
            ),
            cancellation_token=cancellation_token,
        )[0]

    def embed_many(
        self,
        requests: Sequence[EmbeddingBatchRequest],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[EmbeddingBatch, ...]:
        """Embed compatible task members in one provider batch.

        Compatibility is technical: profile identity, model endpoint,
        requested dimensions and cache namespace must agree. ``purpose`` is
        retained only in the returned metadata; it never changes grouping.
        """
        token = cancellation_token or CancellationToken()
        token.raise_if_cancelled()
        if not requests:
            raise EmbeddingRequestError("embedding batch must not be empty")
        first = requests[0]
        if first.profile is None:
            raise EmbeddingRequestError("embedding profile is required")
        for request in requests:
            if request.profile is None:
                raise EmbeddingRequestError("embedding profile is required")
            try:
                validate_embedding_purpose(request.purpose)
            except ValueError as exc:
                raise EmbeddingRequestError(str(exc)) from exc
            if not request.texts:
                raise EmbeddingRequestError("embedding batch must not be empty")
            if request.cache_keys is not None and len(request.cache_keys) != len(request.texts):
                raise EmbeddingRequestError("embedding cache_keys must match texts")
            required_role = {
                "object_candidate_query": "query",
                "object_identity_passage": "passage",
            }.get(request.purpose)
            if required_role is not None and request.role != required_role:
                raise EmbeddingRequestError(
                    f"{request.purpose} requires role={required_role}"
                )
            if (
                request.profile.model != first.profile.model
                or request.profile.base_url != first.profile.base_url
                or request.profile.provider_kind != first.profile.provider_kind
                or request.dimensions != first.dimensions
                or request.cache_namespace != first.cache_namespace
                or request.profile_fingerprint != first.profile_fingerprint
                or request.config_fingerprint != first.config_fingerprint
                or request.privacy_class != first.privacy_class
                or request.deadline != first.deadline
                or request.role != first.role
                or request.renderer_version != first.renderer_version
            ):
                raise EmbeddingRequestError("embedding tasks are not technically compatible")
            for text in request.texts:
                if len(text) > self.max_text_chars:
                    raise EmbeddingTextTooLargeError(
                        f"embedding text of {len(text)} characters exceeds "
                        f"limit {self.max_text_chars}"
                    )

        all_texts = tuple(text for request in requests for text in request.texts)
        if len(all_texts) > self.max_texts:
            raise EmbeddingBatchTooLargeError(
                f"embedding batch of {len(all_texts)} texts exceeds limit {self.max_texts}"
            )

        vectorizer = self._vectorizer_factory()
        identity = self._profile_identity(
            first.profile,
            vectorizer,
            self._vectorizer_dimension(vectorizer),
        )
        keys: list[str | None] = []
        cache_metadata: list[tuple[str, str]] = []
        cached_vectors: list[tuple[float, ...] | None] = []
        for request in requests:
            for index, text in enumerate(request.texts):
                explicit = request.cache_keys[index] if request.cache_keys is not None else ""
                namespace = request.cache_namespace or request.purpose
                key = EmbeddingVectorCache.digest(
                    profile_fingerprint=identity.profile_fingerprint,
                    namespace=namespace,
                    content=explicit or text,
                    role=request.role,
                    renderer_version=request.renderer_version,
                )
                keys.append(key)
                cache_metadata.append((namespace, explicit or text))
                cached_vectors.append(self.cache.get(key) if self.cache is not None else None)
        missing_indices = [index for index, vector in enumerate(cached_vectors) if vector is None]

        request_start = 0
        operation_item_counts: dict[str, int] = {}
        for request in requests:
            operation_item_counts[request.purpose] = operation_item_counts.get(
                request.purpose, 0
            ) + len(request.texts)
        for request in requests:
            request_end = request_start + len(request.texts)
            request_cached = cached_vectors[request_start:request_end]
            record_task(
                kind="embedding",
                operation=request.purpose,
                provider_profile_fingerprint=identity.profile_fingerprint,
                model=first.profile.model,
                task_count=1,
                item_count=len(request.texts),
                cache_hits=sum(vector is not None for vector in request_cached),
                cache_misses=sum(vector is None for vector in request_cached),
            )
            request_start = request_end

        try:
            token.raise_if_cancelled()
            if missing_indices:
                set_context = getattr(vectorizer, "set_telemetry_context", None)
                if callable(set_context):
                    try:
                        set_context(
                            operation=(
                                requests[0].purpose
                                if len(operation_item_counts) == 1
                                else "mixed_embedding_batch"
                            ),
                            profile_fingerprint=identity.profile_fingerprint,
                            operation_item_counts=operation_item_counts,
                        )
                    except TypeError:
                        # Test/local vectorizers may implement the older
                        # two-field hook; attribution remains exact for the
                        # real HTTP vectorizer below.
                        set_context(
                            operation=requests[0].purpose,
                            profile_fingerprint=identity.profile_fingerprint,
                        )
                missing_texts = tuple(
                    all_texts[index] for index in missing_indices
                )
                try:
                    raw_missing = list(
                        vectorizer.encode(missing_texts, role=first.role)
                    )
                except TypeError:
                    # Compatibility is limited to legacy, role-less generic
                    # embeddings.  A required query/passage role is never
                    # retried through a plain call.
                    if first.role is not None:
                        raise
                    raw_missing = list(vectorizer.encode(missing_texts))
            else:
                raw_missing = []
            if len(raw_missing) != len(missing_indices):
                raise EmbeddingModelError("embedding backend returned a partial result")
            vectors = [
                list(vector) if vector is not None else list(raw_missing.pop(0))
                for vector in cached_vectors
            ]
            validated = self._validated_vectors(vectorizer, vectors)
            if self.cache is not None:
                for key, vector, original, metadata in zip(
                    keys, validated, cached_vectors, cache_metadata, strict=True
                ):
                    if original is None and key is not None:
                        namespace, content_digest = metadata
                        self.cache.put(
                            key,
                            vector,
                            profile_fingerprint=identity.profile_fingerprint,
                            namespace=namespace,
                            content_digest=content_digest,
                        )
            dimension = len(validated[0]) if validated else identity.dimensions or 0
            result: list[EmbeddingBatch] = []
            offset = 0
            for request in requests:
                size = len(request.texts)
                result.append(
                    EmbeddingBatch(
                        vectors=tuple(validated[offset : offset + size]),
                        model=first.profile.model,
                        model_version=identity.profile_fingerprint,
                        dimensions=dimension,
                        purpose=request.purpose,
                        role=request.role,
                        renderer_version=request.renderer_version,
                    )
                )
                offset += size
            return tuple(result)
        finally:
            close = getattr(vectorizer, "close", None)
            if callable(close):
                close()

    def _validated_vectors(
        self, vectorizer: Vectorizer, raw_vectors: Sequence[Sequence[float]]
    ) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        expected_dimension = self._vectorizer_dimension(vectorizer)
        for vector in raw_vectors:
            coerced = tuple(float(value) for value in vector)
            if not coerced:
                raise EmbeddingModelError("embedding backend returned an empty vector")
            for value in coerced:
                if not math.isfinite(value):
                    raise EmbeddingNonFiniteError(
                        "embedding vector contains non-finite values"
                    )
            if expected_dimension is not None and len(coerced) != expected_dimension:
                raise EmbeddingDimensionMismatchError(
                    f"embedding dimension {len(coerced)} does not match "
                    f"backend dimension {expected_dimension}"
                )
            vectors.append(coerced)
        dimension = len(vectors[0]) if vectors else 0
        if any(len(vector) != dimension for vector in vectors):
            raise EmbeddingDimensionMismatchError(
                "embedding batch has inconsistent vector dimensions"
            )
        return vectors

    @staticmethod
    def _vectorizer_dimension(vectorizer: Vectorizer) -> int | None:
        try:
            return int(vectorizer.dimension)
        except (RuntimeError, TypeError, ValueError):
            return None

    def _profile_identity(
        self,
        profile: InferenceProfile,
        vectorizer: Vectorizer,
        dimensions: int | None,
    ) -> EmbeddingProfileIdentity:
        try:
            model_version = vectorizer.fingerprint.strip()
        except (AttributeError, RuntimeError, TypeError):
            model_version = ""
        if not model_version or model_version == "unknown":
            raise EmbeddingModelError(
                "embedding backend did not expose a stable model fingerprint"
            )
        config: dict[str, object] = {
            "base_url": profile.base_url,
            "provider_kind": profile.provider_kind,
            "vectorizer": f"{type(vectorizer).__module__}.{type(vectorizer).__qualname__}",
            "max_input_tokens": profile.max_input_tokens,
            **self._identity_config,
        }
        return EmbeddingProfileIdentity(
            model_id=profile.model,
            model_version=model_version,
            dimensions=dimensions,
            config=config,
        )


__all__ = [
    "EmbeddingBatch",
    "EmbeddingBatchRequest",
    "EmbeddingCache",
    "EmbeddingCacheSchemaError",
    "EmbeddingBatchTooLargeError",
    "EmbeddingDimensionMismatchError",
    "EmbeddingError",
    "EmbeddingModelError",
    "EmbeddingNonFiniteError",
    "EmbeddingProfileIdentity",
    "EmbeddingProfileReadiness",
    "EmbeddingProvider",
    "PersistentEmbeddingCache",
    "EmbeddingVectorCache",
    "EmbeddingPurpose",
    "EmbeddingRequestError",
    "EmbeddingTextTooLargeError",
    "VectorizerFactory",
]
