"""Run the bundled local embedding backend on demand."""

from __future__ import annotations

import argparse
import fcntl
import json
import signal
import sys
from pathlib import Path
from threading import Event
from urllib.request import Request, urlopen

from ...inference.gguf_vectorizer import GGUFVectorizer
from ...inference.sentence_transformer_vectorizer import SentenceTransformerVectorizer
from .service import EmbeddingService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="serve a verified local embedding model"
    )
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--model", default=None)
    parser.add_argument("--device", choices=("cuda",), default="cuda")
    parser.add_argument("--embedding-proxy-endpoint")
    parser.add_argument("--embedding-proxy-token-file", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--dimensions", type=int, default=2048)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--token")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--embedding-alias", action="append", default=[])
    parser.add_argument("--reranker-model-path", type=Path)
    parser.add_argument("--reranker-model", default="Qwen/Qwen3-Reranker-0.6B")
    parser.add_argument("--reranker-device", choices=("cuda",), default="cuda")
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=Path("~/.local/share/ledgermind/model-gateway.lock"),
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
        raise RuntimeError("embedding proxy returned a non-object response")
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
    if args.embedding_proxy_endpoint:
        proxy_token = ""
        if args.embedding_proxy_token_file is not None:
            proxy_token = args.embedding_proxy_token_file.read_text(encoding="utf-8").strip()
        health = _proxy_json(args.embedding_proxy_endpoint, proxy_token, "/health/ready")
        if health.get("device") != "cuda":
            raise RuntimeError("embedding proxy is not running on CUDA")
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
            response = _proxy_json(
                args.embedding_proxy_endpoint, proxy_token, "/embeddings", payload
            )
            rows = response.get("data")
            if not isinstance(rows, list) or len(rows) != len(texts):
                raise RuntimeError("embedding proxy returned an invalid batch")
            ordered = sorted(rows, key=lambda row: int(row["index"]))
            return [list(row["embedding"]) for row in ordered]

        backend = proxy_backend
        model = proxy_model
        dimensions = proxy_dimensions
        embedding_fingerprint = proxy_fingerprint
    else:
        if args.model_path is None:
            raise RuntimeError("--model-path or --embedding-proxy-endpoint is required")
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
            )
        backend = vectorizer.encode
        model = args.model or vectorizer.fingerprint
        dimensions = vectorizer.dimension
        embedding_fingerprint = vectorizer.fingerprint
    token = args.token
    if args.token_file is not None:
        token = args.token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError("local embedding token file is empty")
    reranker = None
    if args.reranker_model_path is not None:
        from ledgermind_inference.retrieval_reranker import QwenLocalReranker

        reranker = QwenLocalReranker(args.reranker_model_path, args.reranker_device)
    service = EmbeddingService(
        backend=backend,
        model=model,
        dimensions=dimensions,
        device=args.device,
        host=args.host,
        port=args.port,
        token=token,
        embedding_fingerprint=embedding_fingerprint,
        embedding_aliases=args.embedding_alias,
        reranker=reranker.score if reranker is not None else None,
        reranker_model=args.reranker_model if reranker is not None else None,
    )
    stopped = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    service.start()
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
