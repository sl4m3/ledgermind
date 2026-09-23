"""Minimal OpenAI-compatible local embedding service boundary."""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

EmbeddingBackend = Callable[..., Sequence[Sequence[float]]]


class EmbeddingService:
    """Expose a verified local backend as an offline `/embeddings` endpoint."""

    def __init__(
        self,
        *,
        backend: EmbeddingBackend,
        model: str,
        dimensions: int,
        device: str,
        host: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
    ) -> None:
        self.backend = backend
        self.model = model
        self.dimensions = int(dimensions)
        self.device = device
        self.host = host
        self.port = int(port)
        self.token = token
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def endpoint(self) -> str | None:
        if self._server is None:
            return None
        return f"http://{self.host}:{self._server.server_port}"

    def start(self) -> str:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                del format, args

            def _json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0].rstrip("/")
                if path == "/health" or path.endswith("/health"):
                    self._json(
                        200,
                        {
                            "status": "ok",
                            "model": service.model,
                            "dimensions": service.dimensions,
                            "device": service.device,
                        },
                    )
                    return
                self._json(404, {"error": "not_found"})

            def do_POST(self) -> None:
                path = self.path.split("?", 1)[0].rstrip("/")
                if path != "/embeddings" and not path.endswith("/embeddings"):
                    self._json(404, {"error": "not_found"})
                    return
                if (
                    service.token
                    and self.headers.get("authorization") != f"Bearer {service.token}"
                ):
                    self._json(401, {"error": "unauthorized"})
                    return
                try:
                    length = int(self.headers.get("content-length", "0"))
                    payload = json.loads(self.rfile.read(length))
                    raw_input = (
                        payload.get("input") if isinstance(payload, dict) else None
                    )
                    texts = [raw_input] if isinstance(raw_input, str) else raw_input
                    if not isinstance(texts, list) or not all(
                        isinstance(text, str) for text in texts
                    ):
                        raise ValueError("input must be a string or string array")
                    if isinstance(payload, dict) and payload.get("model") not in {
                        None,
                        service.model,
                    }:
                        raise ValueError("model does not match the configured runtime")
                    raw_role = (
                        payload.get("input_type") if isinstance(payload, dict) else None
                    )
                    if raw_role not in {None, "query", "passage"}:
                        raise ValueError("input_type must be query or passage")
                    vectors = list(
                        service.backend(texts, role=raw_role)
                        if raw_role is not None
                        else service.backend(texts)
                    )
                    if len(vectors) != len(texts):
                        raise ValueError("embedding backend returned an invalid batch")
                    for vector in vectors:
                        if len(vector) != service.dimensions or not all(
                            isinstance(value, (int, float))
                            and math.isfinite(float(value))
                            for value in vector
                        ):
                            raise ValueError(
                                "embedding backend returned an invalid vector"
                            )
                    data = [
                        {
                            "object": "embedding",
                            "index": index,
                            "embedding": list(vector),
                        }
                        for index, vector in enumerate(vectors)
                    ]
                    self._json(
                        200, {"object": "list", "data": data, "model": service.model}
                    )
                except Exception:  # noqa: BLE001
                    self._json(400, {"error": "invalid_embedding_request"})

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="ledgermind-embedding", daemon=True
        )
        self._thread.start()
        return self.endpoint or ""

    def stop(self) -> None:
        server = self._server
        self._server = None
        if server is not None:
            server.shutdown()
            server.server_close()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=2.0)


__all__ = ["EmbeddingService"]
