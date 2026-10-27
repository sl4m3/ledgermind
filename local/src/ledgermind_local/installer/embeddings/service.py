"""Minimal OpenAI-compatible local embedding service boundary."""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

EmbeddingBackend = Callable[..., Sequence[Sequence[float]]]
RerankBackend = Callable[[str, Sequence[str]], Sequence[float]]


class EmbeddingService:
    """Expose verified local models as one offline embedding + rerank endpoint."""

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
        embedding_fingerprint: str | None = None,
        embedding_aliases: Sequence[str] = (),
        reranker: RerankBackend | None = None,
        reranker_model: str | None = None,
        reranker_fingerprint: str | None = None,
    ) -> None:
        self.backend = backend
        self.model = model
        self.embedding_aliases = tuple(str(alias) for alias in embedding_aliases if alias)
        self.dimensions = int(dimensions)
        self.device = device
        self.host = host
        self.port = int(port)
        self.token = token
        # Supplied by the loaded vectorizer, never derived from a served alias.
        self.embedding_fingerprint = embedding_fingerprint
        self.reranker = reranker
        self.reranker_model = reranker_model or ""
        self.reranker_fingerprint = reranker_fingerprint
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
                if path in {"/health/ready", "/v1/health/ready"}:
                    fingerprint = service.embedding_fingerprint
                    if not isinstance(fingerprint, str) or not fingerprint.strip() or fingerprint.strip() == "unknown":
                        self._json(503, {"error": "embedding_identity_unavailable"})
                        return
                    self._json(200, {
                        "status": "ready", "embedding_model": service.model,
                        "embedding_dimensions": service.dimensions,
                        "embedding_fingerprint": fingerprint.strip(), "device": service.device,
                        "reranker_model": service.reranker_model or None,
                        "reranker_loaded": service.reranker is not None,
                        "reranker_device": service.device if service.reranker is not None else None,
                    })
                    return
                if path in {"/health/live", "/v1/health/live"}:
                    self._json(200, {"status": "ok"})
                    return
                if path == "/health" or path.endswith("/health"):
                    self._json(
                        200,
                        {
                            "status": "ok",
                            "model": service.model,
                            "dimensions": service.dimensions,
                            "device": service.device,
                            "embedding": {
                                "model": service.model,
                                "dimensions": service.dimensions,
                                "device": service.device,
                                "loaded": True,
                                "fingerprint": service.embedding_fingerprint,
                            },
                            "reranker": {
                                "model": service.reranker_model or None,
                                "device": service.device if service.reranker is not None else None,
                                "loaded": service.reranker is not None,
                                "fingerprint": service.reranker_fingerprint,
                            },
                        },
                    )
                    return
                self._json(404, {"error": "not_found"})

            def do_POST(self) -> None:
                path = self.path.split("?", 1)[0].rstrip("/")
                is_embedding = path == "/embeddings" or path.endswith("/embeddings")
                is_rerank = path.endswith("/rerank")
                if not is_embedding and not is_rerank:
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
                    if not isinstance(payload, dict):
                        raise ValueError("request body must be an object")
                    if is_rerank:
                        if service.reranker is None:
                            self._json(503, {"error": "reranker_unavailable"})
                            return
                        model = payload.get("model")
                        if model not in {None, service.reranker_model}:
                            raise ValueError("model does not match the configured runtime")
                        query = payload.get("query")
                        documents = payload.get("documents", payload.get("texts"))
                        if not isinstance(query, str) or not query.strip():
                            raise ValueError("query must be a non-empty string")
                        if not isinstance(documents, list) or not all(
                            isinstance(document, str) and document
                            for document in documents
                        ):
                            raise ValueError("documents must be a non-empty string array")
                        if not documents:
                            self._json(200, {
                                "model": service.reranker_model,
                                "results": [],
                            })
                            return
                        scores = list(service.reranker(query, documents))
                        if len(scores) != len(documents):
                            raise ValueError("reranker backend returned an invalid batch")
                        rows = []
                        for index, score in enumerate(scores):
                            if (
                                not isinstance(score, (int, float))
                                or isinstance(score, bool)
                                or not math.isfinite(float(score))
                            ):
                                raise ValueError("reranker backend returned an invalid score")
                            rows.append({
                                "index": index,
                                "relevance_score": float(score),
                            })
                        rows.sort(key=lambda row: (-row["relevance_score"], row["index"]))
                        top_n = payload.get("top_n")
                        if top_n is not None:
                            if (
                                not isinstance(top_n, int)
                                or isinstance(top_n, bool)
                                or not 1 <= top_n <= len(rows)
                            ):
                                raise ValueError("top_n is out of range")
                            rows = rows[:top_n]
                        self._json(200, {
                            "model": service.reranker_model,
                            "results": rows,
                            "usage": {"prompt_tokens": 0, "total_tokens": 0, "cost": 0.0},
                        })
                        return
                    raw_input = payload.get("input")
                    texts = [raw_input] if isinstance(raw_input, str) else raw_input
                    if not isinstance(texts, list) or not all(
                        isinstance(text, str) for text in texts
                    ):
                        raise ValueError("input must be a string or string array")
                    requested_model = payload.get("model")
                    allowed_models = {None, service.model, *service.embedding_aliases}
                    if requested_model not in allowed_models:
                        raise ValueError("model does not match the configured runtime")
                    raw_role = payload.get("input_type")
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
                    self._json(200, {
                        "object": "list",
                        "data": data,
                        "model": requested_model or service.model,
                    })
                except Exception:  # noqa: BLE001
                    self._json(400, {"error": "invalid_rerank_request" if is_rerank else "invalid_embedding_request"})

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
