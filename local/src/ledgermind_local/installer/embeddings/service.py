"""Minimal OpenAI-compatible local embedding service boundary.

Local uses a single FIFO lock: one GPU forward at a time, no priority classes
and no server-side request rejection for normal batches.  Large batches are
split into bounded chunks; the request always returns one complete result or a
clear error.
"""

from __future__ import annotations

import gc
import json
import math
import os
import sys
import threading
import time
import traceback
from collections.abc import Callable, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

EmbeddingBackend = Callable[..., Sequence[Sequence[float]]]
RerankBackend = Callable[[str, Sequence[str]], Sequence[float]]


class BackendUnavailable(RuntimeError):
    """A backend dependency reported a retriable failure (OOM, busy, proxy down)."""

    def __init__(self, code: str) -> None:
        super().__init__(f"embedding backend unavailable: {code}")
        self.code = code


class RequestTooLarge(ValueError):
    """The request exceeds the Local adapter's safety cap."""

    def __init__(self, *, limit: str, actual: int, maximum: int) -> None:
        super().__init__(f"request {limit} {actual} exceeds limit {maximum}")
        self.limit = limit
        self.actual = actual
        self.maximum = maximum


def _is_cuda_oom(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    return "outofmemory" in name or "out of memory" in str(exc).lower()


class EmbeddingService:
    """Expose verified local models as one offline embedding + rerank endpoint."""

    def __init__(
        self,
        *,
        backend: EmbeddingBackend | None = None,
        model: str = "",
        dimensions: int = 0,
        device: str = "cpu",
        host: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
        embedding_fingerprint: str | None = None,
        embedding_aliases: Sequence[str] = (),
        reranker: RerankBackend | None = None,
        reranker_model: str | None = None,
        reranker_device: str | None = None,
        reranker_fingerprint: str | None = None,
        max_request_texts: int = 512,
        max_request_chars: int = 1_000_000,
        max_request_documents: int = 256,
        chunk_texts: int = 8,
        queue_timeout: float = 10.0,
        idle_unload_seconds: float | None = None,
        vectorizer: Any | None = None,
        vectorizer_factory: Callable[[], Any] | None = None,
        backend_factory: Callable[[], EmbeddingBackend] | None = None,
        reranker_instance: Any | None = None,
        reranker_factory: Callable[[], Any] | None = None,
    ) -> None:
        if max_request_texts < 1:
            raise ValueError("max_request_texts must be positive")
        if max_request_chars < 1:
            raise ValueError("max_request_chars must be positive")
        if max_request_documents < 1:
            raise ValueError("max_request_documents must be positive")
        if chunk_texts < 1:
            raise ValueError("chunk_texts must be positive")
        if queue_timeout <= 0:
            raise ValueError("queue_timeout must be positive")
        self._vectorizer = vectorizer
        if self._vectorizer is None and backend is not None:
            self._vectorizer = getattr(backend, "__self__", None)
        self._vectorizer_factory = vectorizer_factory
        self._backend_factory = backend_factory
        self._saved_backend = backend
        self._backend = backend

        self._raw_reranker = reranker_instance
        if self._raw_reranker is None and reranker is not None:
            self._raw_reranker = getattr(reranker, "__self__", None)
        self._reranker_factory = reranker_factory
        self._saved_reranker = reranker
        self._reranker = reranker

        self.max_request_texts = int(max_request_texts)
        self.max_request_chars = int(max_request_chars)
        self.max_request_documents = int(max_request_documents)
        self.chunk_texts = max(1, int(chunk_texts))
        self.queue_timeout = float(queue_timeout)
        self._gpu_lock = threading.Lock()
        self._activity_lock = threading.Lock()
        self._active_requests = 0
        self.last_activity = time.monotonic()
        self.model = model
        self.embedding_aliases = tuple(
            str(alias) for alias in embedding_aliases if alias
        )
        self.dimensions = int(dimensions)
        self.device = device
        self.host = host
        self.port = int(port)
        self.token = token
        # Supplied by the loaded vectorizer, never derived from a served alias.
        self.embedding_fingerprint = embedding_fingerprint
        self.reranker_model = reranker_model or ""
        self.reranker_device = reranker_device or (
            device if reranker is not None else None
        )
        self.reranker_fingerprint = reranker_fingerprint

        if idle_unload_seconds is None:
            env_val = os.environ.get(
                "LEDGERMIND_EMBEDDING_IDLE_UNLOAD_SECONDS"
            ) or os.environ.get("LEDGERMIND_IDLE_UNLOAD_SECONDS")
            if env_val:
                try:
                    idle_unload_seconds = float(env_val)
                except ValueError:
                    idle_unload_seconds = 60.0
            else:
                idle_unload_seconds = 60.0
        self.idle_unload_seconds = float(idle_unload_seconds)
        self.unload_policy_active = True
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._idle_thread: threading.Thread | None = None
        self._idle_stop: threading.Event | None = None

    @property
    def backend(self) -> EmbeddingBackend | None:
        return self._backend

    @backend.setter
    def backend(self, val: EmbeddingBackend | None) -> None:
        self._backend = val
        if val is not None:
            self._saved_backend = val
            if self._vectorizer is None:
                self._vectorizer = getattr(val, "__self__", None)

    @property
    def reranker(self) -> RerankBackend | None:
        return self._reranker

    @reranker.setter
    def reranker(self, val: RerankBackend | None) -> None:
        self._reranker = val
        if val is not None:
            self._saved_reranker = val
            if self._raw_reranker is None:
                self._raw_reranker = getattr(val, "__self__", None)

    @property
    def loaded(self) -> bool:
        return self._backend is not None or self._reranker is not None

    @property
    def embedding_loaded(self) -> bool:
        return self._backend is not None

    @property
    def reranker_loaded(self) -> bool:
        return self._reranker is not None

    def _ensure_backend_loaded(self) -> None:
        if self._backend is not None:
            return
        with self._gpu_lock:
            if self._backend is not None:
                return
            if self._vectorizer_factory is not None:
                self._vectorizer = self._vectorizer_factory()
                self._backend = getattr(self._vectorizer, "encode", self._vectorizer)
            elif self._backend_factory is not None:
                self._backend = self._backend_factory()
            elif self._saved_backend is not None:
                self._backend = self._saved_backend

    def _ensure_reranker_loaded(self) -> None:
        if self._reranker is not None:
            return
        with self._gpu_lock:
            if self._reranker is not None:
                return
            if self._reranker_factory is not None:
                self._raw_reranker = self._reranker_factory()
                self._reranker = getattr(
                    self._raw_reranker, "score", self._raw_reranker
                )
            elif self._saved_reranker is not None:
                self._reranker = self._saved_reranker

    def unload_idle(self, force: bool = False) -> bool:
        """Unload models if idle timeout expired and no requests in flight."""
        if self.is_busy and not force:
            return False
        if not force and self.idle_unload_seconds <= 0:
            return False
        now = time.monotonic()
        if not force and self.idle_unload_seconds > 0:
            if self.last_activity > 0 and (
                now - self.last_activity < self.idle_unload_seconds
            ):
                return False
        if not self.loaded:
            return False
        # A backend supplied directly (including serve.py's embedding-proxy
        # path) has no factory that can rebuild it.  Unloading it would make
        # every later request fail with embedding_unavailable, so only drop
        # components that can be lazily reconstructed.  force=True is an
        # explicit shutdown-style request and may drop them anyway.
        can_reload_embedding = (
            self._vectorizer_factory is not None or self._backend_factory is not None
        )
        unload_embedding = self._backend is not None and (force or can_reload_embedding)
        unload_reranker = self._reranker is not None and (
            force or self._reranker_factory is not None
        )
        if not unload_embedding and not unload_reranker:
            return False
        acquired = self._gpu_lock.acquire(timeout=2.0)
        if not acquired:
            return False
        try:
            if self.is_busy and not force:
                return False
            if unload_embedding:
                if self._vectorizer is not None and hasattr(self._vectorizer, "close"):
                    try:
                        self._vectorizer.close()
                    except Exception:  # noqa: BLE001, S110
                        pass
                self._vectorizer = None
                self._backend = None
                self._saved_backend = None

            if unload_reranker:
                if self._raw_reranker is not None and hasattr(
                    self._raw_reranker, "close"
                ):
                    try:
                        self._raw_reranker.close()
                    except Exception:  # noqa: BLE001, S110
                        pass
                self._raw_reranker = None
                self._reranker = None
                self._saved_reranker = None

            gc.collect()
            self.release_cuda_cache()
            return True
        finally:
            self._gpu_lock.release()

    check_idle_unload = unload_idle

    def _idle_monitor_loop(self) -> None:
        interval = (
            min(1.0, max(0.05, self.idle_unload_seconds / 5.0))
            if self.idle_unload_seconds > 0
            else 1.0
        )
        while self._idle_stop is not None and not self._idle_stop.wait(interval):
            if self.unload_policy_active and self.idle_unload_seconds > 0:
                if not self.is_busy and self.loaded:
                    now = time.monotonic()
                    if self.last_activity > 0 and (
                        now - self.last_activity >= self.idle_unload_seconds
                    ):
                        self.unload_idle(force=False)

    @property
    def endpoint(self) -> str | None:
        if self._server is None:
            return None
        return f"http://{self.host}:{self._server.server_port}"

    @property
    def is_busy(self) -> bool:
        with self._activity_lock:
            return self._active_requests > 0

    def begin_request(self) -> None:
        with self._activity_lock:
            self._active_requests += 1
        self.last_activity = time.monotonic()

    def end_request(self) -> None:
        with self._activity_lock:
            self._active_requests = max(0, self._active_requests - 1)
        self.last_activity = time.monotonic()

    def _validate_batch(self, texts: Sequence[str]) -> None:
        if len(texts) > self.max_request_texts:
            raise RequestTooLarge(
                limit="texts",
                actual=len(texts),
                maximum=self.max_request_texts,
            )
        chars = sum(len(text) for text in texts)
        if chars > self.max_request_chars:
            raise RequestTooLarge(
                limit="chars",
                actual=chars,
                maximum=self.max_request_chars,
            )

    def _chunks(self, texts: Sequence[str]) -> list[list[str]]:
        return [
            list(texts[start : start + self.chunk_texts])
            for start in range(0, len(texts), self.chunk_texts)
        ]

    def _encode_chunk(self, chunk: list[str], role: str | None) -> list[list[float]]:
        return list(
            self.backend(chunk, role=role) if role is not None else self.backend(chunk)
        )

    def encode(self, texts: Sequence[str], role: str | None) -> list[list[float]]:
        """Run one FIFO embedding request; chunks are internal and ordered."""
        if self._backend is None:
            self._ensure_backend_loaded()
        if self._backend is None:
            raise BackendUnavailable("embedding_unavailable")
        self.last_activity = time.monotonic()
        values = list(texts)
        if not values:
            return []
        self._validate_batch(values)
        deadline = time.monotonic() + self.queue_timeout
        if not self._gpu_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            raise BackendUnavailable("busy")
        try:
            vectors: list[list[float]] = []
            for chunk in self._chunks(values):
                try:
                    vectors.extend(self._encode_chunk(chunk, role))
                except BaseException as exc:
                    if isinstance(exc, BackendUnavailable):
                        raise
                    if not _is_cuda_oom(exc):
                        if isinstance(
                            exc, (RuntimeError, OSError, ImportError, TimeoutError)
                        ):
                            raise BackendUnavailable("backend_error") from exc
                        raise
                    self.release_cuda_cache()
                    if len(chunk) <= 1:
                        raise BackendUnavailable("cuda_out_of_memory") from exc
                    half = len(chunk) // 2
                    try:
                        vectors.extend(self._encode_chunk(chunk[:half], role))
                        vectors.extend(self._encode_chunk(chunk[half:], role))
                    except BaseException as retry_exc:
                        if isinstance(retry_exc, BackendUnavailable):
                            raise
                        if _is_cuda_oom(retry_exc):
                            self.release_cuda_cache()
                            raise BackendUnavailable(
                                "cuda_out_of_memory"
                            ) from retry_exc
                        if isinstance(
                            retry_exc,
                            (RuntimeError, OSError, ImportError, TimeoutError),
                        ):
                            raise BackendUnavailable("backend_error") from retry_exc
                        raise
            return vectors
        finally:
            self._gpu_lock.release()

    def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Run one rerank request under the same FIFO GPU lock."""
        if self._reranker is None:
            self._ensure_reranker_loaded()
        if self._reranker is None:
            raise BackendUnavailable("reranker_unavailable")
        self.last_activity = time.monotonic()
        values = list(documents)
        if not values:
            return []
        if len(values) > self.max_request_documents:
            raise RequestTooLarge(
                limit="documents",
                actual=len(values),
                maximum=self.max_request_documents,
            )
        deadline = time.monotonic() + self.queue_timeout
        if not self._gpu_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            raise BackendUnavailable("busy")
        try:
            try:
                return list(self.reranker(query, values))
            except BaseException as exc:
                if isinstance(exc, BackendUnavailable):
                    raise
                if _is_cuda_oom(exc):
                    self.release_cuda_cache()
                    raise BackendUnavailable("cuda_out_of_memory") from exc
                if isinstance(exc, (RuntimeError, OSError, ImportError, TimeoutError)):
                    raise BackendUnavailable("backend_error") from exc
                raise
        finally:
            self._gpu_lock.release()

    def release_cuda_cache(self) -> None:
        """Drop cached CUDA allocations while idle (allocator never returns them otherwise)."""
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001, S110 - cache release is best effort
            pass

    def start(self) -> str:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                del format, args

            def _json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    return

            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0].rstrip("/")
                if path in {"/health/ready", "/v1/health/ready"}:
                    fingerprint = service.embedding_fingerprint
                    is_configured = (
                        service.loaded
                        or service._saved_backend is not None
                        or service._vectorizer_factory is not None
                        or service._backend_factory is not None
                        or service._saved_reranker is not None
                        or service._reranker_factory is not None
                        or bool(service.model)
                    )
                    if (
                        service._backend is not None
                        or service._saved_backend is not None
                    ) and (
                        not isinstance(fingerprint, str)
                        or not fingerprint.strip()
                        or fingerprint.strip() == "unknown"
                    ):
                        self._json(503, {"error": "embedding_identity_unavailable"})
                        return
                    if not is_configured:
                        self._json(503, {"error": "backend_unavailable"})
                        return
                    self._json(
                        200,
                        {
                            "status": "ready",
                            "unload_policy_active": service.unload_policy_active,
                            "idle_unload_seconds": service.idle_unload_seconds,
                            "loaded": service.loaded,
                            "embedding_loaded": service.embedding_loaded,
                            "embedding_model": service.model or None,
                            "embedding_dimensions": service.dimensions or None,
                            "embedding_fingerprint": (
                                fingerprint.strip()
                                if isinstance(fingerprint, str) and fingerprint.strip()
                                else None
                            ),
                            "device": service.device,
                            "reranker_model": service.reranker_model or None,
                            "reranker_loaded": service.reranker_loaded,
                            "reranker_device": service.reranker_device,
                        },
                    )
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
                            "unload_policy_active": service.unload_policy_active,
                            "idle_unload_seconds": service.idle_unload_seconds,
                            "loaded": service.loaded,
                            "embedding": {
                                "model": service.model
                                if (
                                    service._backend is not None
                                    or service._saved_backend is not None
                                    or service._vectorizer_factory is not None
                                    or service._backend_factory is not None
                                )
                                else None,
                                "dimensions": service.dimensions
                                if (
                                    service._backend is not None
                                    or service._saved_backend is not None
                                    or service._vectorizer_factory is not None
                                    or service._backend_factory is not None
                                )
                                else None,
                                "device": service.device
                                if (
                                    service._backend is not None
                                    or service._saved_backend is not None
                                    or service._vectorizer_factory is not None
                                    or service._backend_factory is not None
                                )
                                else None,
                                "loaded": service.embedding_loaded,
                                "fingerprint": service.embedding_fingerprint,
                            },
                            "reranker": {
                                "model": service.reranker_model or None,
                                "device": (
                                    service.reranker_device
                                    if (
                                        service._reranker is not None
                                        or service._saved_reranker is not None
                                        or service._reranker_factory is not None
                                    )
                                    else None
                                ),
                                "loaded": service.reranker_loaded,
                                "fingerprint": service.reranker_fingerprint,
                            },
                        },
                    )
                    return
                self._json(404, {"error": "not_found"})

            def _handle_rerank(self, payload: dict[str, Any]) -> None:
                if (
                    service._reranker is None
                    and service._saved_reranker is None
                    and service._reranker_factory is None
                ):
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
                    isinstance(document, str) and document for document in documents
                ):
                    raise ValueError("documents must be a non-empty string array")
                if not documents:
                    self._json(200, {"model": service.reranker_model, "results": []})
                    return
                scores = service.rerank(query, documents)
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
                    rows.append({"index": index, "relevance_score": float(score)})
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
                self._json(
                    200,
                    {
                        "model": service.reranker_model,
                        "results": rows,
                        "usage": {
                            "prompt_tokens": 0,
                            "total_tokens": 0,
                            "cost": 0.0,
                        },
                    },
                )

            def _handle_embedding(self, payload: dict[str, Any]) -> None:
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
                vectors = service.encode(texts, raw_role)
                if len(vectors) != len(texts):
                    raise ValueError("embedding backend returned an invalid batch")
                for vector in vectors:
                    if len(vector) != service.dimensions or not all(
                        isinstance(value, (int, float)) and math.isfinite(float(value))
                        for value in vector
                    ):
                        raise ValueError("embedding backend returned an invalid vector")
                data = [
                    {
                        "object": "embedding",
                        "index": index,
                        "embedding": list(vector),
                    }
                    for index, vector in enumerate(vectors)
                ]
                self._json(
                    200,
                    {
                        "object": "list",
                        "data": data,
                        "model": requested_model or service.model,
                    },
                )

            def do_POST(self) -> None:
                service.begin_request()
                try:
                    path = self.path.split("?", 1)[0].rstrip("/")
                    is_embedding = path == "/embeddings" or path.endswith("/embeddings")
                    is_rerank = path.endswith("/rerank")
                    if not is_embedding and not is_rerank:
                        self._json(404, {"error": "not_found"})
                        return
                    if (
                        service.token
                        and self.headers.get("authorization")
                        != f"Bearer {service.token}"
                    ):
                        self._json(401, {"error": "unauthorized"})
                        return
                    try:
                        length = int(self.headers.get("content-length", "0"))
                        payload = json.loads(self.rfile.read(length))
                        if not isinstance(payload, dict):
                            raise ValueError(  # noqa: TRY004 - mapped to HTTP 400
                                "request body must be an object"
                            )
                        if is_rerank:
                            self._handle_rerank(payload)
                        else:
                            self._handle_embedding(payload)
                    except RequestTooLarge as exc:
                        self._json(
                            413,
                            {
                                "error": "request_too_large",
                                "limit": exc.limit,
                                "actual": exc.actual,
                                "maximum": exc.maximum,
                            },
                        )
                    except BackendUnavailable as exc:
                        self._json(503, {"error": exc.code})
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    except ValueError:
                        self._json(
                            400,
                            {
                                "error": (
                                    "invalid_rerank_request"
                                    if is_rerank
                                    else "invalid_embedding_request"
                                )
                            },
                        )
                    except Exception:  # noqa: BLE001 - unexpected errors are 500
                        traceback.print_exc(file=sys.stderr)
                        self._json(500, {"error": "internal_error"})
                finally:
                    service.end_request()

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="ledgermind-embedding",
            daemon=True,
        )
        self._thread.start()
        if self.unload_policy_active and self.idle_unload_seconds > 0:
            self._idle_stop = threading.Event()
            self._idle_thread = threading.Thread(
                target=self._idle_monitor_loop,
                name="ledgermind-idle-unload",
                daemon=True,
            )
            self._idle_thread.start()
        return self.endpoint or ""

    def stop(self) -> None:
        if self._idle_stop is not None:
            self._idle_stop.set()
        if self._idle_thread is not None:
            self._idle_thread.join(timeout=2.0)
            self._idle_thread = None
        self._idle_stop = None
        server = self._server
        self._server = None
        if server is not None:
            server.shutdown()
            server.server_close()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=2.0)


__all__ = ["BackendUnavailable", "EmbeddingService", "RequestTooLarge"]
