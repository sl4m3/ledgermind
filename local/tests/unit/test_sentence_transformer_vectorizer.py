from __future__ import annotations

from pathlib import Path

from ledgermind_local.inference.sentence_transformer_vectorizer import (
    SentenceTransformerVectorizer,
)


class _Rows(list[list[float]]):
    def tolist(self) -> list[list[float]]:
        return list(self)


class _Tokenizer:
    def encode(self, text: str, *, add_special_tokens: bool = True) -> list[int]:
        assert add_special_tokens is True
        return [0] * len(text)


class _Model:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.batch_sizes: list[int | None] = []
        self.tokenizer = _Tokenizer()

    def get_sentence_embedding_dimension(self) -> int:
        return 3

    def encode_query(self, texts: list[str], **kwargs: object) -> _Rows:
        self.calls.append(("query", texts))
        self.batch_sizes.append(kwargs.get("batch_size"))  # type: ignore[arg-type]
        return _Rows([[1.0, 2.0, 3.0] for _ in texts])

    def encode_document(self, texts: list[str], **kwargs: object) -> _Rows:
        self.calls.append(("passage", texts))
        self.batch_sizes.append(kwargs.get("batch_size"))  # type: ignore[arg-type]
        return _Rows([[3.0, 2.0, 1.0] for _ in texts])


def test_sentence_transformer_vectorizer_preserves_query_passage_roles(
    tmp_path: Path,
) -> None:
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    model = _Model()
    vectorizer = SentenceTransformerVectorizer(
        model_path=tmp_path,
        device="cpu",
        expected_dimension=3,
        model_builder=lambda _path, _device: model,
    )

    assert vectorizer.encode(["find"], role="query") == [[1.0, 2.0, 3.0]]
    assert vectorizer.encode(["knowledge"], role="passage") == [[3.0, 2.0, 1.0]]
    assert model.calls == [("query", ["find"]), ("passage", ["knowledge"])]


def test_sentence_transformer_vectorizer_uses_small_batches_for_mixed_lengths(
    tmp_path: Path,
) -> None:
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    model = _Model()
    vectorizer = SentenceTransformerVectorizer(
        model_path=tmp_path,
        device="cpu",
        expected_dimension=3,
        model_builder=lambda _path, _device: model,
    )

    vectorizer.encode(["short"] * 8, role="passage")
    vectorizer.encode(["short"] * 8 + ["x" * 1000], role="passage")
    vectorizer.encode(["x" * 1000] * 8, role="passage")

    assert model.batch_sizes == [8, 4, 8]


def test_sentence_transformer_vectorizer_counts_texts_over_the_model_window(
    tmp_path: Path,
) -> None:
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    model = _Model()
    vectorizer = SentenceTransformerVectorizer(
        model_path=tmp_path,
        device="cpu",
        expected_dimension=3,
        max_seq_length=10,
        model_builder=lambda _path, _device: model,
    )

    vectorizer.encode(["x" * 20], role="passage")
    vectorizer.encode(["x" * 5], role="passage")

    assert vectorizer.truncated_texts == 1
