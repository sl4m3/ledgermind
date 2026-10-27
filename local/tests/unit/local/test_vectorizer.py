"""Tests for the Local technical vectorizer contract."""

from __future__ import annotations

from collections.abc import Sequence

from ledgermind_local.inference.vectorizer import Vectorizer


class _TestVectorizer:
    """Simple deterministic fake vectorizer for contract tests."""

    def __init__(
        self, *, dimension: int, fingerprint: str, partial: bool = False
    ) -> None:
        self._dimension = dimension
        self._fingerprint = fingerprint
        self._partial = partial
        self.closed = False

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        if self._partial:
            return [(1.0,) * self._dimension] * max(0, len(texts) - 1)
        return [(float(len(text)),) * self._dimension for text in texts]

    def close(self) -> None:
        self.closed = True


def _assert_complete_vectors(
    vectorizer: Vectorizer, texts: list[str]
) -> list[tuple[float, ...]]:
    vectors = vectorizer.encode(texts)
    if len(vectors) != len(texts):
        raise ValueError("partial vectorization result")
    return vectors


def test_vectorizer_fake_implements_required_properties() -> None:
    vectorizer = _TestVectorizer(dimension=3, fingerprint="m1")
    vectors = _assert_complete_vectors(vectorizer, ["a", "bb"])

    assert vectorizer.fingerprint == "m1"
    assert vectorizer.dimension == 3
    assert vectors == [(1.0, 1.0, 1.0), (2.0, 2.0, 2.0)]


def test_vectorizer_dimension() -> None:
    vectorizer = _TestVectorizer(dimension=4, fingerprint="m2")
    vectors = _assert_complete_vectors(vectorizer, ["a"])

    assert vectorizer.dimension == 4
    assert len(vectors[0]) == 4


def test_vectorizer_accepts_empty_batch() -> None:
    vectorizer = _TestVectorizer(dimension=2, fingerprint="m3")
    vectors = _assert_complete_vectors(vectorizer, [])

    assert vectors == []


def test_vectorizer_rejects_partial_results() -> None:
    vectorizer = _TestVectorizer(dimension=2, fingerprint="m4", partial=True)

    try:
        _assert_complete_vectors(vectorizer, ["a", "bb"])
    except ValueError as exc:
        assert str(exc) == "partial vectorization result"
    else:
        raise AssertionError("partial vectorization result was not detected")


def test_fingerprint_is_stable() -> None:
    vectorizer = _TestVectorizer(dimension=2, fingerprint="stable")
    assert vectorizer.fingerprint == "stable"
    assert vectorizer.fingerprint == "stable"
