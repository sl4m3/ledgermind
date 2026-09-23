"""Run the bundled local embedding backend on demand."""

from __future__ import annotations

import argparse
import signal
from pathlib import Path
from threading import Event

from ...inference.gguf_vectorizer import GGUFVectorizer
from ...inference.sentence_transformer_vectorizer import SentenceTransformerVectorizer
from .service import EmbeddingService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="serve a verified local embedding model"
    )
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--device", choices=("cpu", "cuda", "rocm"), default="cpu")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--dimensions", type=int, default=2048)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--token")
    parser.add_argument("--token-file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
    token = args.token
    if args.token_file is not None:
        token = args.token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError("local embedding token file is empty")
    service = EmbeddingService(
        backend=vectorizer.encode,
        model=args.model or vectorizer.fingerprint,
        dimensions=vectorizer.dimension,
        device=args.device,
        host=args.host,
        port=args.port,
        token=token,
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
        vectorizer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
