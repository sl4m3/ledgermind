"""Idle unload must never destroy a backend that cannot be lazily rebuilt."""

from __future__ import annotations

import json
import time
from urllib.request import Request, urlopen

from ledgermind_local.installer.embeddings.service import EmbeddingService


def _wait_for(predicate, *, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def _post(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    request = Request(
        url + "/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read())


def test_direct_backend_is_not_unloaded_without_a_factory() -> None:
    """Proxy/direct backends have no factory; dropping them would break reload."""
    service = EmbeddingService(
        backend=lambda texts, role=None: [[1.0, 2.0] for _ in texts],
        model="proxy-model",
        dimensions=2,
        port=0,
        embedding_fingerprint="sha256:test",
        idle_unload_seconds=0.05,
    )
    url = service.start()
    try:
        assert service._idle_thread is not None
        time.sleep(0.2)
        assert service.loaded is True, "direct backend must survive the idle monitor"
        status, body = _post(url, {"model": "proxy-model", "input": ["hello"]})
        assert status == 200
        assert body["data"][0]["embedding"] == [1.0, 2.0]
    finally:
        service.stop()


def test_factory_backend_unloads_and_reloads_transparently() -> None:
    made: list[object] = []

    class Vectorizer:
        def __init__(self) -> None:
            self.closed = False

        def encode(self, texts, role=None):
            return [[3.0, 4.0] for _ in texts]

        def close(self) -> None:
            self.closed = True

    def factory() -> Vectorizer:
        vectorizer = Vectorizer()
        made.append(vectorizer)
        return vectorizer

    service = EmbeddingService(
        vectorizer_factory=factory,
        model="local-model",
        dimensions=2,
        port=0,
        embedding_fingerprint="sha256:test",
        idle_unload_seconds=0.05,
    )
    url = service.start()
    try:
        status, _ = _post(url, {"model": "local-model", "input": ["first"]})
        assert status == 200
        assert len(made) == 1
        first = made[0]
        assert _wait_for(lambda: service.loaded is False), "idle monitor did not unload"
        assert first.closed is True

        status, body = _post(url, {"model": "local-model", "input": ["second"]})
        assert status == 200
        assert body["data"][0]["embedding"] == [3.0, 4.0]
        assert len(made) == 2, "request must rebuild the backend from the factory"
    finally:
        service.stop()


def test_inflight_request_blocks_idle_unload() -> None:
    made: list[object] = []

    class Vectorizer:
        def __init__(self) -> None:
            self.closed = False

        def encode(self, texts, role=None):
            return [[5.0, 6.0] for _ in texts]

        def close(self) -> None:
            self.closed = True

    def factory() -> Vectorizer:
        vectorizer = Vectorizer()
        made.append(vectorizer)
        return vectorizer

    service = EmbeddingService(
        vectorizer_factory=factory,
        model="local-model",
        dimensions=2,
        port=0,
        embedding_fingerprint="sha256:test",
        idle_unload_seconds=0.05,
    )
    service.start()
    try:
        status, _ = _post(
            service.endpoint, {"model": "local-model", "input": ["first"]}
        )
        assert status == 200
        service.begin_request()
        try:
            time.sleep(0.2)
            assert service.loaded is True
            assert made[0].closed is False
        finally:
            service.end_request()
        assert _wait_for(lambda: service.loaded is False)
        assert made[0].closed is True
    finally:
        service.stop()
