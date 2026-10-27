from __future__ import annotations

import os
import time

import pytest
from ledgermind_local.config import RerankerConfig
from ledgermind_local.inference.retrieval_reranker import (
    TOKEN_RE,
    ApiReranker,
    QwenWorkerReranker,
    adaptive_k_cutoff,
    candidate_document,
    pack_items,
    pack_items_with_dependencies,
    rank_items,
    rank_items_with_scores,
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
        if query is None:
            connection.send(("counts", [len(text) for text in documents]))
        elif query == "hang":
            time.sleep(3)
        elif query == "slow":
            time.sleep(0.3)
            connection.send(("scores", [1.0 for _ in documents]))
        elif query == "exit":
            connection.close()
            return
        else:
            connection.send(("scores", [float(index) for index, _ in enumerate(documents)]))


def _items() -> list[dict[str, object]]:
    return [{"value_id": f"item{index}", "object_name": "Project", "facet": "constraint",
             "content": f"Rule {index} is required.", "conditions": []}
            for index in range(1, 9)]


def _injection() -> dict[str, object]:
    return {"text": "How to read memory:\nThese are saved facts.\nconstraint — a rule.\n\nM1: x",
            "legend": ["constraint — a rule."]}


def test_adaptive_k_largest_drop_and_flat_distribution():
    assert adaptive_k_cutoff([0.95, 0.9, 0.3, 0.2]) == (2, pytest.approx(0.6))
    assert adaptive_k_cutoff([1.0, 0.5, 0.0]) == (1, 0.5)
    assert adaptive_k_cutoff([0.5, 0.5, 0.5]) == (3, 0.0)
    assert adaptive_k_cutoff([]) == (0, 0.0)
    assert adaptive_k_cutoff([0.7]) == (1, 0.0)
    with pytest.raises(ValueError, match="finite"):
        adaptive_k_cutoff([float("nan")])
    with pytest.raises(ValueError, match="descending"):
        adaptive_k_cutoff([0.1, 0.9])


def test_adaptive_k_is_default_with_explicit_legacy_opt_out():
    assert RerankerConfig().selection_policy == "adaptive_k"
    assert RerankerConfig(selection_policy="hybrid").selection_policy == "hybrid"
    with pytest.raises(ValueError):
        RerankerConfig(selection_policy="unknown")


def test_adaptive_k_preserves_whole_records_and_one_hop_dependencies():
    items = _items()
    original_contents = [item["content"] for item in items]
    scores = dict(zip([item["value_id"] for item in items],
                      [0.95, 0.9, 0.3, 0.25, 0.2, 0.15, 0.1, 0.05]))
    selected, _, tokens, diagnostics = pack_items_with_dependencies(
        items, _injection(), None, selection_policy="adaptive_k", reranker_scores=scores,
        dependency_links={"item1": ["item7"], "item7": ["item8"]},
    )
    assert [item["value_id"] for item in selected] == ["item1", "item2", "item7"]
    assert diagnostics["base_value_ids"] == ["item1", "item2"]
    assert diagnostics["dependency_value_ids"] == ["item7"]
    assert diagnostics["adaptive_k_cutoff"] == 2
    assert tokens <= 1024
    assert [item["content"] for item in items] == original_contents


def test_adaptive_k_hard_budget_omits_without_truncation():
    items = _items()
    selected, _, tokens, diagnostics = pack_items_with_dependencies(
        items, _injection(), None, selection_policy="adaptive_k",
        reranker_scores={item["value_id"]: 0.5 for item in items},
        token_counter=lambda text: text.count("is required.") * 100,
        hard_budget=250,
    )
    assert len(selected) == 2
    assert tokens == 200
    assert len(diagnostics["omitted_base"]) == 6


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


def test_rank_scores_preserved_without_mutating_candidates():
    import copy
    items = _items()
    original = copy.deepcopy(items)
    ranked, scores = rank_items_with_scores("rules", items, _Scores())
    assert items == original
    assert [r["value_id"] for r in ranked] == [r["value_id"] for r in scores]
    assert scores[0]["reranker_score"] == 0.9
    assert scores[0]["core_position"] == 1


def test_packer_uses_injected_tokenizer_and_keeps_minimum_whole():
    counter = lambda text: len(text.encode("utf-8"))
    minimum = counter(render_injection(_items()[:6], _injection(), "ru")["text"])
    items, injection, tokens = pack_items(_items(), _injection(), "ru",
        soft_budget=minimum, token_counter=counter)
    assert len(items) == 6
    assert tokens == counter(injection["text"])


def test_injection_groups_repeated_object_facets_without_losing_ranked_claims():
    items = [
        {"value_id": "v1", "primary_object_id": "object-a", "object_name": "Agent A",
         "facet": "state", "content": "Initial state is retained.", "conditions": []},
        {"value_id": "v2", "primary_object_id": "object-b", "object_name": "Agent B",
         "facet": "event", "content": "An independent event happened.", "conditions": []},
        {"value_id": "v3", "primary_object_id": "object-a", "object_name": "Agent A",
         "facet": "state", "content": "Current state is healthy.",
         "conditions": [{"surface_text": "after verification"}]},
    ]
    original = {
        "text": "How to read memory:\nThese are saved facts.\nstate — current state.\nevent — history.",
        "legend": ["state — current state.", "event — history."],
    }

    rendered = render_injection(items, original, "en")
    text = rendered["text"]

    assert rendered["item_count"] == 3
    assert text.count("[state] Agent A") == 1
    assert text.count("[event] Agent B") == 1
    assert "M1: Initial state is retained." in text
    assert "M2: [event] Agent B: An independent event happened." in text
    assert "M3: Current state is healthy. | when after verification" in text
    assert text.index("G1: [state] Agent A:") < text.index("M2: [event] Agent B:")
    assert render_injection(items, original, "en") == rendered


def test_grouped_packing_preserves_whole_long_claim_and_uses_final_rendering_budget():
    items = _items()
    for item in items:
        item["primary_object_id"] = "project"
    items[0]["content"] = "begin " + ("unchanged-token " * 80) + "end"
    minimum = len(TOKEN_RE.findall(render_injection(items[:6], _injection(), "en")["text"]))

    selected, injection, tokens = pack_items(
        items, _injection(), "en", soft_budget=minimum + 12,
    )

    assert [item["value_id"] for item in selected[:6]] == [f"item{i}" for i in range(1, 7)]
    assert "begin " in injection["text"] and " end" in injection["text"]
    assert injection["text"].count("unchanged-token") == 80
    assert tokens == len(TOKEN_RE.findall(injection["text"]))
    assert tokens <= minimum + 12 or len(selected) == 6


def test_same_display_name_with_distinct_core_objects_is_not_grouped():
    items = [
        {"value_id": "v1", "primary_object_id": "object-a", "object_name": "Worker",
         "facet": "state", "content": "First worker is ready.", "conditions": []},
        {"value_id": "v2", "primary_object_id": "object-b", "object_name": "Worker",
         "facet": "state", "content": "Second worker is paused.", "conditions": []},
    ]
    original = {
        "text": "How to read memory:\nThese are saved facts.\nstate — current state.",
        "legend": ["state — current state."],
    }

    rendered = render_injection(items, original, "en")["text"]

    assert rendered.count("[state] Worker") == 2
    assert "G1:" not in rendered
    assert "M1: [state] Worker: First worker is ready." in rendered
    assert "M2: [state] Worker: Second worker is paused." in rendered


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


def test_core_dependencies_survive_soft_budget_without_recursion_or_score_boost():
    import copy
    items = _items()
    original = copy.deepcopy(items)
    base, _, before = pack_items(items, _injection(), "en", soft_budget=1)
    selected, injection, count, diagnostics = pack_items_with_dependencies(
        items, _injection(), "en", soft_budget=1,
        dependency_links={"item1": ["item7", "item7"], "item7": ["item8"]},
    )
    assert selected[:6] == base
    assert [item["value_id"] for item in selected] == [f"item{i}" for i in range(1, 8)]
    assert diagnostics["dependency_value_ids"] == ["item7"]
    assert diagnostics["context_tokens_before_expansion"] == before
    assert diagnostics["context_tokens_after_expansion"] == count > before
    assert count == len(TOKEN_RE.findall(injection["text"]))
    assert diagnostics["dependency_items_omitted"] == 0
    assert diagnostics["injection_rendering"] == "object_facet_groups_v1"
    assert diagnostics["injection_group_count"] == 1
    assert diagnostics["injection_claim_count"] == 7
    assert items == original


def test_dependency_budget_omissions_are_explicit_and_minimum_stays_whole():
    selected, _, count, diagnostics = pack_items_with_dependencies(
        _items(), _injection(), "en", soft_budget=1, hard_budget=5,
        dependency_links={"item1": ["item7", "not-in-pool"]},
    )
    assert len(selected) == 6 and count > 5
    assert diagnostics["minimum_exceeds_hard_budget"] is True
    assert diagnostics["omitted_dependencies"] == [
        {"value_id": "not-in-pool", "reason": "outside_candidate_pool"},
        {"value_id": "item7", "reason": "whole_dependency_exceeds_budget"},
    ]


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


def test_cpu_worker_default_wait_is_unlimited_and_dead_worker_is_detected() -> None:
    worker = QwenWorkerReranker("unused", "cpu", worker_target=_fake_worker)
    try:
        assert worker.startup_timeout is None
        assert worker.score_timeout is None
        assert worker.score("slow", ["a"]) == [1.0]
        with pytest.raises((EOFError, RuntimeError)):
            worker.score("exit", ["a"])
        assert worker.score("ok", ["a"]) == [0.0]
    finally:
        worker.close()


def test_worker_timeout_terminates_child_and_next_request_recovers() -> None:
    worker = QwenWorkerReranker(
        "unused", "cpu", startup_timeout=2, score_timeout=0.2,
        worker_target=_fake_worker,
    )
    try:
        assert worker.score("ok", ["a", "b"]) == [0.0, 1.0]
        assert worker.count_tokens("abc") == 3
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
