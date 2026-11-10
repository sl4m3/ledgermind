"""Run the bundled local embedding backend on demand."""

from __future__ import annotations

import argparse
import fcntl
import json
import signal
import sys
from pathlib import Path
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ...inference.gguf_vectorizer import GGUFVectorizer
from ...inference.sentence_transformer_vectorizer import SentenceTransformerVectorizer
from .service import BackendUnavailable, EmbeddingService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="serve verified local embedding and reranker models"
    )
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--model", default=None)
    parser.add_argument("--device", choices=("cpu", "cuda", "rocm"), default="cpu")
    parser.add_argument("--embedding-proxy-endpoint")
    parser.add_argument("--embedding-proxy-token-file", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--dimensions", type=int, default=2048)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--max-request-texts", type=int, default=512)
    parser.add_argument("--max-request-chars", type=int, default=1_000_000)
    parser.add_argument("--max-request-docs", type=int, default=256)
    parser.add_argument("--chunk-texts", type=int, default=8)
    parser.add_argument("--queue-timeout", type=float, default=10.0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--token")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--embedding-alias", action="append", default=[])
    parser.add_argument("--reranker-model-path", type=Path)
    parser.add_argument("--reranker-model", default="Qwen/Qwen3-Reranker-0.6B")
    parser.add_argument(
        "--reranker-device", choices=("cpu", "cuda", "rocm"), default="cpu"
    )
    parser.add_argument("--reranker-runtime", type=Path)
    parser.add_argument(
        "--idle-unload-seconds",
        type=float,
        default=None,
        help="Seconds of idle before unloading model from memory",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=Path("~/.local/share/ledgermind/embedding.lock"),
    )
    return parser


def _proxy_json(
    endpoint: str,
    token: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    url = endpoint.rstrip("/") + path
    headers = {"accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["content-type"] = "application/json"
    if token:
        headers["authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise RuntimeError(  # noqa: TRY004 - protocol violation, not caller input
            "embedding proxy returned a non-object response"
        )
    return body


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    lock_handle = None
    if args.lock_file is not None:
        lock_path = args.lock_file.expanduser()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = lock_path.open("a+")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("model gateway is already running", file=sys.stderr)
            lock_handle.close()
            return 0
    vectorizer = None
    backend = None
    model = args.model or ""
    dimensions = args.dimensions
    embedding_fingerprint: str | None = None
    if args.model_path is not None and not args.embedding_proxy_endpoint:
        print(
            f"local embedding max_seq_length={args.max_seq_length} "
            f"chunk_texts={args.chunk_texts}",
            flush=True,
        )
    if args.embedding_proxy_endpoint:
        proxy_token = ""
        if args.embedding_proxy_token_file is not None:
            proxy_token = args.embedding_proxy_token_file.read_text(
                encoding="utf-8"
            ).strip()
        health = _proxy_json(
            args.embedding_proxy_endpoint, proxy_token, "/health/ready"
        )
        proxy_model = str(health["embedding_model"])
        proxy_dimensions = int(health["embedding_dimensions"])
        proxy_fingerprint = str(health.get("embedding_fingerprint") or "")
        if not proxy_fingerprint:
            raise RuntimeError("embedding proxy has no identity fingerprint")

        def proxy_backend(texts: list[str], role: str | None = None):
            payload: dict[str, object] = {
                "model": proxy_model,
                "input": list(texts),
            }
            if role is not None:
                payload["input_type"] = role
            try:
                response = _proxy_json(
                    args.embedding_proxy_endpoint, proxy_token, "/embeddings", payload
                )
            except HTTPError as exc:
                if exc.code not in {429, 502, 503, 504}:
                    raise
                code = "proxy_unavailable"
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                    if isinstance(body, dict) and isinstance(body.get("error"), str):
                        code = str(body["error"])
                except (ValueError, OSError):
                    if exc.code == 429:
                        code = "busy"
                raise BackendUnavailable(code) from exc
            rows = response.get("data")
            if not isinstance(rows, list) or len(rows) != len(texts):
                raise RuntimeError("embedding proxy returned an invalid batch")
            ordered = sorted(rows, key=lambda row: int(row["index"]))
            return [list(row["embedding"]) for row in ordered]

        backend = proxy_backend
        model = proxy_model
        dimensions = proxy_dimensions
        embedding_fingerprint = proxy_fingerprint
    elif args.model_path is not None:
        if args.model_path.suffix.lower() == ".gguf":
            vectorizer = GGUFVectorizer(
                model_path=args.model_path,
                n_threads=args.threads,
                gpu_layers=args.gpu_layers,
            )
        else:
            vectorizer = SentenceTransformerVectorizer(
                model_path=args.model_path,
                device=args.device,
                expected_dimension=args.dimensions,
                max_seq_length=args.max_seq_length,
            )
        backend = vectorizer.encode
        model = args.model or vectorizer.fingerprint
        dimensions = vectorizer.dimension
        embedding_fingerprint = vectorizer.fingerprint
    elif args.reranker_model_path is None:
        raise RuntimeError(
            "--model-path, --embedding-proxy-endpoint, or --reranker-model-path is required"
        )
    token = args.token
    if args.token_file is not None:
        token = args.token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError("local embedding token file is empty")
    reranker = None
    if args.reranker_model_path is not None:
        if args.reranker_runtime is not None:
            site_packages = args.reranker_runtime.expanduser() / "site-packages"
            if site_packages.is_dir() and str(site_packages) not in sys.path:
                sys.path.insert(0, str(site_packages))
        from ledgermind_inference.retrieval_reranker import QwenLocalReranker

        reranker = QwenLocalReranker(args.reranker_model_path, args.reranker_device)
    service = EmbeddingService(
        backend=backend,
        model=model,
        dimensions=dimensions,
        device=args.device if backend is not None else args.reranker_device,
        host=args.host,
        port=args.port,
        token=token,
        embedding_fingerprint=embedding_fingerprint,
        embedding_aliases=args.embedding_alias,
        reranker=reranker.score if reranker is not None else None,
        reranker_model=args.reranker_model if reranker is not None else None,
        reranker_device=args.reranker_device if reranker is not None else None,
        max_request_texts=args.max_request_texts,
        max_request_chars=args.max_request_chars,
        max_request_documents=args.max_request_docs,
        chunk_texts=args.chunk_texts,
        queue_timeout=args.queue_timeout,
        idle_unload_seconds=args.idle_unload_seconds,
    )
    stopped = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopped.set()

    def _idle_cache_reaper() -> None:
        # The CUDA caching allocator holds peak memory indefinitely; release
        # it once per idle period, never while a request is in flight.
        import time

        last_release = 0.0
        while not stopped.wait(10.0):
            if service.is_busy:
                continue
            now = time.monotonic()
            if (
                now - service.last_activity >= 60.0
                and service.last_activity > last_release
            ):
                service.release_cuda_cache()
                last_release = now

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    service.start()
    Thread(
        target=_idle_cache_reaper, name="ledgermind-cache-reaper", daemon=True
    ).start()
    try:
        stopped.wait()
    finally:
        service.stop()
        if vectorizer is not None:
            vectorizer.close()
        if lock_handle is not None:
            lock_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
