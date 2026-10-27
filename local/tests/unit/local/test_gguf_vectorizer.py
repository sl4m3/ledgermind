"""Tests for GGUF-backed local vectorizer adapter."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ledgermind_local.inference.gguf_vectorizer import GGUFVectorizer


class _FakeModel:
    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[tuple[str, int | None]] = []
        self.closed = 0

    def create_embedding(
        self, text: str, *, n_threads: int | None = None
    ) -> dict[str, Any]:
        self.calls.append((text, n_threads))
        if not self._vectors:
            return {"embedding": []}
        return {"embedding": self._vectors.pop(0)}

    def close(self) -> None:
        self.closed += 1


def _builder_factory(
    vectors: list[list[float]],
) -> tuple[Callable[[str, int, int], _FakeModel], _FakeModel]:
    model = _FakeModel(vectors)

    def _builder(model_path: str, n_threads: int, gpu_layers: int) -> _FakeModel:
        assert model_path
        assert gpu_layers == 0
        return model

    return _builder, model


def test_gguf_vectorizer_loads_model_lazily() -> None:
    builder, _model = _builder_factory([[0.1, 0.2]])
    vectorizer = GGUFVectorizer(
        model_path=Path("/tmp/model.gguf"),
        n_threads=2,
        model_builder=builder,
        manifest={"dimension": 2, "model_fingerprint": "f"},
    )

    assert vectorizer.fingerprint == "f"
    assert vectorizer.dimension == 2
    assert vectorizer.encode([]) == []


def test_gguf_vectorizer_encodes_and_closes_idempotently() -> None:
    vectors = [
        [1.0, 1.0],
        [2.0, 2.0],
    ]
    builder, model = _builder_factory(vectors)
    vectorizer = GGUFVectorizer(
        model_path="/tmp/model.gguf",
        n_threads=1,
        manifest={"dimension": 2},
        model_builder=builder,
    )

    encoded = vectorizer.encode(["a", "b"])
    assert len(encoded) == 2
    vectorizer.close()
    vectorizer.close()

    assert model.closed == 1
    assert model.calls == [("a", 1), ("b", 1)]


def test_gguf_vectorizer_raises_on_partial_embedding() -> None:
    builder, _model = _builder_factory([[1.0, 2.0], [3.0]])
    vectorizer = GGUFVectorizer(
        model_path="/tmp/model.gguf",
        manifest={"dimension": 2},
        model_builder=builder,
    )

    with pytest.raises(ValueError, match="partial embedding"):
        vectorizer.encode(["a", "b"])


def test_gguf_vectorizer_rejects_wrong_prefix() -> None:
    with pytest.raises(ValueError, match="model prefix"):
        GGUFVectorizer(
            model_path="/tmp/my-model.gguf",
            model_prefix="expected",
            model_builder=lambda path, n_threads, gpu_layers: _FakeModel([[1.0, 1.0]]),
        )
