"""Local adapter FIFO, chunking and error-contract tests."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ledgermind_local.installer.embeddings.service import (
    BackendUnavailable,
    EmbeddingService,
)


def _post(
    url: str, path: str, payload: dict[str, object]
) -> tuple[int, dict[str, object]]:
    request = Request(
        url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "authorization": "Bearer test-token",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _service(backend, **kwargs) -> EmbeddingService:
    defaults = {
        "model": "nemotron",
        "dimensions": 2,
        "device": "cuda",
        "port": 0,
        "token": "test-token",
        "embedding_fingerprint": "sha256:test",
    }
    defaults.update(kwargs)
    return EmbeddingService(backend=backend, **defaults)


def test_large_batch_is_chunked_and_order_is_preserved() -> None:
    chunks: list[int] = []

    def backend(texts, role=None):
        del role
        chunks.append(len(texts))
        return [[float(len(text)), 1.0] for text in texts]

    service = _service(backend, chunk_texts=2, max_request_texts=10)
    url = service.start()
    try:
        status, body = _post(
            url,
            "/embeddings",
            {"model": "nemotron", "input": [f"text-{index}" for index in range(5)]},
        )
    finally:
        service.stop()
    assert status == 200
    assert chunks == [2, 2, 1]
    assert [row["index"] for row in body["data"]] == [0, 1, 2, 3, 4]
    assert [row["embedding"][0] for row in body["data"]] == [
        float(len(f"text-{index}")) for index in range(5)
    ]


def test_stock_batches_32_and_128_are_accepted() -> None:
    def backend(texts, role=None):
        del role
        return [[float(len(text)), 1.0] for text in texts]

    service = _service(backend, chunk_texts=8, max_request_texts=512)
    url = service.start()
    try:
        for count in (32, 128):
            status, body = _post(
                url,
                "/embeddings",
                {
                    "model": "nemotron",
                    "input": [f"text-{index}" for index in range(count)],
                },
            )
            assert status == 200, body
            assert len(body["data"]) == count
            assert [row["index"] for row in body["data"]] == list(range(count))
    finally:
        service.stop()


def test_fifo_lock_serializes_concurrent_requests() -> None:
    active = 0
    maximum = 0
    guard = threading.Lock()

    def backend(texts, role=None):
        nonlocal active, maximum
        del role
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return [[float(len(text)), 1.0] for text in texts]

    service = _service(backend, chunk_texts=4)
    url = service.start()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda index: _post(
                        url,
                        "/embeddings",
                        {"model": "nemotron", "input": f"request-{index}"},
                    ),
                    range(2),
                )
            )
    finally:
        service.stop()
    assert [status for status, _ in results] == [200, 200]
    assert maximum == 1


def test_request_cap_returns_413_and_never_calls_backend() -> None:
    calls: list[int] = []

    def backend(texts, role=None):
        del role
        calls.append(len(texts))
        return [[1.0, 1.0] for _ in texts]

    service = _service(backend, max_request_texts=2)
    url = service.start()
    try:
        status, body = _post(
            url,
            "/embeddings",
            {"model": "nemotron", "input": ["a", "b", "c"]},
        )
    finally:
        service.stop()
    assert status == 413
    assert body["error"] == "request_too_large"
    assert calls == []


def test_rerank_request_cap_returns_413() -> None:
    service = _service(
        lambda texts, role=None: [[1.0, 1.0] for _ in texts],
        reranker=lambda query, documents: [0.5 for _ in documents],
        reranker_model="Qwen/Qwen3-Reranker-0.6B",
        max_request_documents=2,
    )
    url = service.start()
    try:
        status, body = _post(
            url,
            "/rerank",
            {
                "model": "Qwen/Qwen3-Reranker-0.6B",
                "query": "backup",
                "documents": ["a", "b", "c"],
            },
        )
    finally:
        service.stop()
    assert status == 413
    assert body["error"] == "request_too_large"


def test_backend_error_is_503_not_400() -> None:
    def backend(texts, role=None):
        del texts, role
        raise RuntimeError("model exploded")

    service = _service(backend)
    url = service.start()
    try:
        status, body = _post(
            url,
            "/embeddings",
            {"model": "nemotron", "input": "one"},
        )
    finally:
        service.stop()
    assert status == 503
    assert body["error"] == "backend_error"


def test_cuda_oom_is_503_with_stable_code() -> None:
    def backend(texts, role=None):
        del texts, role
        raise RuntimeError("CUDA out of memory while allocating")

    service = _service(backend)
    url = service.start()
    try:
        status, body = _post(
            url,
            "/embeddings",
            {"model": "nemotron", "input": "one"},
        )
    finally:
        service.stop()
    assert status == 503
    assert body["error"] == "cuda_out_of_memory"


def test_proxy_backend_unavailable_keeps_its_code() -> None:
    def backend(texts, role=None):
        del texts, role
        raise BackendUnavailable("busy")

    service = _service(backend)
    url = service.start()
    try:
        status, body = _post(
            url,
            "/embeddings",
            {"model": "nemotron", "input": "one"},
        )
    finally:
        service.stop()
    assert status == 503
    assert body["error"] == "busy"
