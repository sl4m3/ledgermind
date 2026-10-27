from __future__ import annotations

from collections.abc import Sequence

import pytest

from ledgermind_local.inference.cancellation import CancellationToken
from ledgermind_local.inference.embedding_provider import (
    EmbeddingBatchTooLargeError,
    EmbeddingCacheSchemaError,
    EmbeddingDimensionMismatchError,
    EmbeddingModelError,
    EmbeddingNonFiniteError,
    EmbeddingProvider,
    EmbeddingRequestError,
    EmbeddingTextTooLargeError,
    PersistentEmbeddingCache,
)
from ledgermind_local.inference.profiles import InferenceProfile
from ledgermind_local.inference.providers.base import ProviderCancelledError
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations


class _FakeVectorizer:
    def __init__(
        self,
        *,
        dimension: int,
        fingerprint: str,
        vectors: list[list[float]] | None = None,
        partial: bool = False,
        closed: list[bool] | None = None,
    ) -> None:
        self._dimension = dimension
        self._fingerprint = fingerprint
        self._vectors = vectors
        self._partial = partial
        self._closed = closed

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if self._partial:
            return [[0.0] * self._dimension] * max(0, len(texts) - 1)
        if self._vectors is not None:
            return self._vectors
        return [[float(len(text))] * self._dimension for text in texts]

    def close(self) -> None:
        if self._closed is not None:
            self._closed.append(True)


def _profile() -> InferenceProfile:
    return InferenceProfile(
        profile_id="embedding-default",
        base_url="https://provider.example/v1",
        model="embed-model",
        secret_ref="embed-secret",
    )


def _provider(
    vectorizer: _FakeVectorizer,
    *,
    max_texts: int = 64,
    max_text_chars: int = 8_000,
) -> EmbeddingProvider:
    return EmbeddingProvider(
        vectorizer_factory=lambda: vectorizer, max_texts=max_texts,
        max_text_chars=max_text_chars,
    )


def test_embed_returns_batch_with_model_metadata() -> None:
    vectorizer = _FakeVectorizer(dimension=3, fingerprint="sha256:abc")
    provider = _provider(vectorizer)
    identity = provider.describe_profile(_profile())
    batch = provider.embed(["first text", "second"], _profile(), "knowledge")

    assert len(batch.vectors) == 2
    assert all(len(vector) == 3 for vector in batch.vectors)
    assert batch.dimensions == 3
    assert batch.model == "embed-model"
    assert batch.model_version == identity.profile_fingerprint
    assert batch.model_version.startswith("sha256:")
    assert batch.purpose == "knowledge"


def test_profile_fingerprint_is_stable_and_secret_free() -> None:
    profile = _profile()
    provider = _provider(_FakeVectorizer(dimension=3, fingerprint="sha256:abc"))

    first = provider.describe_profile(profile)
    second = provider.describe_profile(profile)

    assert first == second
    assert "embed-secret" not in first.model_dump_json()
    assert first.to_core_metadata()["embedding_model_version"] == first.profile_fingerprint


def test_embed_closes_vectorizer_after_use() -> None:
    closed: list[bool] = []
    vectorizer = _FakeVectorizer(dimension=2, fingerprint="m1", closed=closed)

    _provider(vectorizer).embed(["text"], _profile(), "knowledge")

    assert closed == [True]


def test_embed_rejects_empty_batch() -> None:
    vectorizer = _FakeVectorizer(dimension=2, fingerprint="m1")

    with pytest.raises(EmbeddingRequestError):
        _provider(vectorizer).embed([], _profile(), "knowledge")


def test_embed_rejects_batch_over_limit() -> None:
    vectorizer = _FakeVectorizer(dimension=2, fingerprint="m1")

    with pytest.raises(EmbeddingBatchTooLargeError):
        _provider(vectorizer, max_texts=2).embed(
            ["a", "b", "c"], _profile(), "knowledge"
        )


def test_embed_rejects_oversized_text() -> None:
    vectorizer = _FakeVectorizer(dimension=2, fingerprint="m1")

    with pytest.raises(EmbeddingTextTooLargeError):
        _provider(vectorizer, max_text_chars=4).embed(
            ["way too long"], _profile(), "knowledge"
        )


def test_embed_rejects_non_finite_vectors() -> None:
    vectorizer = _FakeVectorizer(
        dimension=2, fingerprint="m1", vectors=[[1.0, float("nan")], [2.0, 2.0]]
    )

    with pytest.raises(EmbeddingNonFiniteError) as error:
        _provider(vectorizer).embed(["a", "b"], _profile(), "knowledge")

    assert error.value.code == "embedding_non_finite"


def test_embed_rejects_vector_dimension_mismatch_with_backend() -> None:
    vectorizer = _FakeVectorizer(
        dimension=3, fingerprint="m1", vectors=[[1.0, 2.0], [3.0, 4.0]]
    )

    with pytest.raises(EmbeddingDimensionMismatchError) as error:
        _provider(vectorizer).embed(["a", "b"], _profile(), "knowledge")

    assert error.value.code == "embedding_dimension_mismatch"


def test_embed_rejects_inconsistent_batch_dimensions() -> None:
    vectorizer = _FakeVectorizer(
        dimension=None,  # dimension unknown, backend returns mixed widths
        fingerprint="m1",
        vectors=[[1.0, 2.0], [1.0, 2.0, 3.0]],
    )

    with pytest.raises(EmbeddingDimensionMismatchError):
        _provider(vectorizer).embed(["a", "b"], _profile(), "knowledge")


def test_embed_rejects_partial_backend_result() -> None:
    vectorizer = _FakeVectorizer(dimension=2, fingerprint="m1", partial=True)

    with pytest.raises(EmbeddingModelError) as error:
        _provider(vectorizer).embed(["a", "b", "c"], _profile(), "knowledge")

    assert error.value.code == "embedding_model_error"


def test_embed_rejects_pre_cancelled_token() -> None:
    vectorizer = _FakeVectorizer(dimension=2, fingerprint="m1")
    token = CancellationToken()
    token.cancel()

    with pytest.raises(ProviderCancelledError):
        _provider(vectorizer).embed(
            ["text"], _profile(), "knowledge", cancellation_token=token
        )


def test_embed_validates_constructor_limits() -> None:
    with pytest.raises(ValueError):
        _provider(_FakeVectorizer(dimension=2, fingerprint="m1"), max_texts=0)
    with pytest.raises(ValueError):
        _provider(_FakeVectorizer(dimension=2, fingerprint="m1"), max_text_chars=0)


def test_persistent_embedding_cache_survives_restart_and_is_profile_scoped(tmp_path) -> None:
    class _CountingVectorizer(_FakeVectorizer):
        def __init__(self) -> None:
            super().__init__(dimension=2, fingerprint="m1")
            self.calls = 0

        def encode(self, texts: Sequence[str]) -> list[list[float]]:
            self.calls += 1
            return super().encode(texts)

    database = tmp_path / "rounds.db"
    connection = open_sqlite_connection(database)
    try:
        rounds_migrations.apply_migrations(connection)
    finally:
        connection.close()
    first_vectorizer = _CountingVectorizer()
    first = EmbeddingProvider(
        vectorizer_factory=lambda: first_vectorizer,
        cache=PersistentEmbeddingCache(database),
    )
    first.embed(["stable facet text"], _profile(), "facet_catalog")
    assert first_vectorizer.calls == 1

    restarted_vectorizer = _CountingVectorizer()
    restarted = EmbeddingProvider(
        vectorizer_factory=lambda: restarted_vectorizer,
        cache=PersistentEmbeddingCache(database),
    )
    restarted.embed(["stable facet text"], _profile(), "facet_catalog")
    assert restarted_vectorizer.calls == 0
    assert restarted.cache is not None
    assert restarted.cache.hits == 1

    other_profile = _profile().model_copy(update={"model": "other-embed-model"})
    isolated_vectorizer = _CountingVectorizer()
    isolated = EmbeddingProvider(
        vectorizer_factory=lambda: isolated_vectorizer,
        cache=PersistentEmbeddingCache(database),
    )
    isolated.embed(["stable facet text"], other_profile, "facet_catalog")
    assert isolated_vectorizer.calls == 1


def test_persistent_embedding_cache_does_not_create_unversioned_schema(tmp_path) -> None:
    with pytest.raises(EmbeddingCacheSchemaError, match="apply Local migrations"):
        PersistentEmbeddingCache(tmp_path / "unmigrated.db")
