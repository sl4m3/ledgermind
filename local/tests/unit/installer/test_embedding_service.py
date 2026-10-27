"""The local model boundary exposes both shared model operations."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from ledgermind_local.installer.embeddings.service import EmbeddingService


def _post(url: str, path: str, payload: dict[str, object], token: str = "") -> dict[str, object]:
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    request = Request(
        url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_service_serves_embedding_alias_and_rerank() -> None:
    service = EmbeddingService(
        backend=lambda texts, role=None: [[float(len(text)), 1.0] for text in texts],
        model="nemotron-3-embed-1b-bf16",
        dimensions=2,
        device="cuda",
        port=0,
        token="test-token",
        embedding_fingerprint="sha256:test",
        embedding_aliases=("nvidia/nemotron-3-embed-1b-local-bf16",),
        reranker=lambda query, documents: [0.9 if "backup" in item else 0.1 for item in documents],
        reranker_model="Qwen/Qwen3-Reranker-0.6B",
    )
    url = service.start()
    try:
        embedding = _post(
            url,
            "/embeddings",
            {
                "model": "nvidia/nemotron-3-embed-1b-local-bf16",
                "input": ["abc"],
            },
            token="test-token",
        )
        assert embedding["model"] == "nvidia/nemotron-3-embed-1b-local-bf16"
        assert embedding["data"][0]["embedding"] == [3.0, 1.0]

        rerank = _post(
            url,
            "/rerank",
            {
                "model": "Qwen/Qwen3-Reranker-0.6B",
                "query": "backup",
                "documents": ["backup the database", "sunny weather"],
            },
            token="test-token",
        )
        assert rerank["results"] == [
            {"index": 0, "relevance_score": 0.9},
            {"index": 1, "relevance_score": 0.1},
        ]

        with urlopen(url + "/health", timeout=10) as response:
            health = json.loads(response.read())
        assert health["embedding"]["fingerprint"] == "sha256:test"
        assert health["reranker"]["loaded"] is True
        assert health["reranker"]["device"] == "cuda"
    finally:
        service.stop()
