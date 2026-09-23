from __future__ import annotations

import os
import time

import pytest

from ledgermind_local.config import RerankerConfig
from ledgermind_local.inference.retrieval_reranker import (
    TOKEN_RE,
    ApiReranker,
    QwenWorkerReranker,
    candidate_document,
    pack_items,
    rank_items,
    render_injection,
)


def test_api_reranker_restores_provider_order_to_input_order(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ]
            }

    captured: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> Response:
        captured.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr("httpx.post", post)
    scorer = ApiReranker(
        "https://reranker.example/v1/rerank", "secret", "rerank-model",
        timeout_seconds=10,
    )

    assert scorer.score("query", ["first", "second"]) == [0.2, 0.9]
    assert captured["url"] == "https://reranker.example/v1/rerank"
    assert captured["json"] == {
        "model": "rerank-model",
        "query": "query",
        "documents": ["first", "second"],
        "top_n": 2,
    }


def test_api_reranker_rejects_partial_provider_response(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"results": [{"index": 0, "relevance_score": 0.9}]}

    monkeypatch.setattr("httpx.post", lambda *_args, **_kwargs: Response())
    scorer = ApiReranker(
        "https://reranker.example/v1/rerank", "secret", "rerank-model",
        timeout_seconds=10,
    )
    with pytest.raises(ValueError, match="incomplete"):
        scorer.score("query", ["first", "second"])


def test_api_reranker_supports_nvidia_reranking_envelope(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"rankings": [{"index": 0, "logit": 1.5}]}

    captured: dict[str, object] = {}

    def post(_url: str, **kwargs: object) -> Response:
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("httpx.post", post)
    scorer = ApiReranker(
        "https://ai.api.nvidia.com/v1/retrieval/nvidia/reranking",
        "secret",
        "nvidia/reranker",
        timeout_seconds=10,
    )
    assert scorer.score("query", ["document"]) == [1.5]
    assert captured["json"] == {
        "model": "nvidia/reranker",
        "query": {"text": "query"},
        "passages": [{"text": "document"}],
    }


def _fake_worker(connection: object, model_path: str, device: str) -> None:
    del model_path, device
    connection.send(("ready", None))
    while True:
        query, documents = connection.recv()
        if query == "hang":
            time.sleep(3)
        else:
            connection.send(("scores", [float(index) for index, _ in enumerate(documents)]))


def _items() -> list[dict[str, object]]:
    return [{"value_id": f"item{index}", "object_name": "Project", "facet": "constraint",
             "content": f"Rule {index} is required.", "conditions": []}
            for index in range(1, 9)]


def _injection() -> dict[str, object]:
    return {"text": "How to read memory:\nThese are saved facts.\nconstraint — a rule.\n\nM1: x",
            "legend": ["constraint — a rule."]}


class _Scores:
    def score(self, query: str, documents: list[str]) -> list[float]:
        assert query == "rules"
        assert all("object: Project" in document for document in documents)
        return [0.5, 0.9, 0.9, 0.1, 0.2, 0.3, 0.8, 0.7]


def test_reranking_stable_ties_and_complete_items() -> None:
    ranked = rank_items("rules", _items(), _Scores())
    assert [row["value_id"] for row in ranked[:3]] == ["item2", "item3", "item7"]
    selected, injection, count = pack_items(ranked, _injection(), "en", soft_budget=1)
    assert len(selected) == 6
    assert injection["item_count"] == 6
    assert count == len(TOKEN_RE.findall(injection["text"]))
    assert "Rule 2 is required." in injection["text"]
    assert "Rule 5 is required." not in injection["text"]


def test_candidate_document_prefers_exact_value_scope() -> None:
    item = {**_items()[0], "scope_text": "only repository A",
            "target_breadcrumb": ["other", "scope"]}
    document = candidate_document(item)
    assert "scope: only repository A" in document
    assert "other / scope" not in document


def test_long_seventh_is_skipped_for_short_eighth() -> None:
    items = _items()
    items[6]["content"] = "long " * 250
    minimum = len(TOKEN_RE.findall(render_injection(items[:6], _injection(), "en")["text"]))
    selected, _, _ = pack_items(items, _injection(), "en", soft_budget=minimum + 12)
    assert [row["value_id"] for row in selected] == ["item1", "item2", "item3", "item4", "item5", "item6", "item8"]


def test_invalid_scores_rejected() -> None:
    class Broken:
        def score(self, query: str, documents: list[str]) -> list[float]:
            return [float("nan")] * len(documents)

    try:
        rank_items("rules", _items(), Broken())
    except ValueError as exc:
        assert "non-finite" in str(exc)
    else:
        raise AssertionError("invalid scores were accepted")


def test_reranker_requires_explicit_local_model_when_enabled() -> None:
    assert not RerankerConfig().enabled
    try:
        RerankerConfig(enabled=True, device="cpu")
    except ValueError as exc:
        assert "model_path" in str(exc)
    else:
        raise AssertionError("missing local model path was accepted")


def test_worker_timeout_terminates_child_and_next_request_recovers() -> None:
    worker = QwenWorkerReranker(
        "unused", "cpu", startup_timeout=2, score_timeout=0.2,
        worker_target=_fake_worker,
    )
    try:
        assert worker.score("ok", ["a", "b"]) == [0.0, 1.0]
        try:
            worker.score("hang", ["a"])
        except TimeoutError:
            pass
        else:
            raise AssertionError("hung worker did not time out")
        assert worker.score("ok", ["a"]) == [0.0]
    finally:
        worker.close()


@pytest.mark.skipif(
    not os.environ.get("LEDGERMIND_TEST_QWEN_SNAPSHOT"),
    reason="requires a predownloaded pinned local model",
)
def test_real_local_qwen_worker_without_provider_calls() -> None:
    worker = QwenWorkerReranker(
        os.environ["LEDGERMIND_TEST_QWEN_SNAPSHOT"], "cpu",
        runtime_path=os.environ.get("LEDGERMIND_TEST_RERANKER_RUNTIME"),
    )
    try:
        scores = worker.score("release procedure", [
            "object: Release\nfacet: procedure\ncontent: Run checks before publish.",
        ])
        assert len(scores) == 1
        assert 0 <= scores[0] <= 1
    finally:
        worker.close()
