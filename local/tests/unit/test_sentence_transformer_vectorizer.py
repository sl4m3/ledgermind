from __future__ import annotations

from pathlib import Path

from ledgermind_local.inference.sentence_transformer_vectorizer import (
    SentenceTransformerVectorizer,
)


class _Rows(list[list[float]]):
    def tolist(self) -> list[list[float]]:
        return list(self)


class _Model:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return 3

    def encode_query(self, texts: list[str], **_kwargs: object) -> _Rows:
        self.calls.append(("query", texts))
        return _Rows([[1.0, 2.0, 3.0] for _ in texts])

    def encode_document(self, texts: list[str], **_kwargs: object) -> _Rows:
        self.calls.append(("passage", texts))
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
