"""GGUF-backed Local technical embedding adapter."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, TypeAlias

from .vectorizer import EmbeddingRole, Vectorizer, VectorizerRoleError

_EmbeddingModelBuilder: TypeAlias = Callable[[str, int, int], Any]


class _EmbeddingModel(Protocol):
    def close(self) -> None: ...

    def create_embedding(self, text: str, *, n_threads: int | None = None) -> Any: ...


def _default_embedding_model_builder(
    model_path: str, n_threads: int, gpu_layers: int
) -> Any:
    try:
        from llama_cpp import Llama
    except ModuleNotFoundError as exc:
        raise RuntimeError("llama_cpp is required for GGUFVectorizer") from exc

    return Llama(
        model_path=model_path,
        embedding=True,
        verbose=False,
        n_threads=n_threads,
        n_gpu_layers=gpu_layers,
    )


def _extract_embedding(result: Any) -> list[float]:
    if isinstance(result, Mapping):
        if "embedding" in result:
            return list(result["embedding"])
        if "data" in result:
            return list(result["data"])
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        return [float(value) for value in result]
    raise RuntimeError("llama embedding returned unsupported payload type")


def _read_uint64(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class GGUFVectorizer(Vectorizer):
    """Adapter over llama_cpp embeddings model."""

    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        n_threads: int = 4,
        gpu_layers: int = 0,
        model_prefix: str | None = None,
        manifest: Mapping[str, Any] | None = None,
        model_builder: _EmbeddingModelBuilder | None = None,
    ) -> None:
        if n_threads <= 0:
            raise ValueError("n_threads must be positive")

        config_model_path = (
            str(manifest["model_path"])
            if manifest and manifest.get("model_path") is not None
            else None
        )
        resolved_manifest_fingerprint = (
            str(manifest["model_fingerprint"])
            if manifest and manifest.get("model_fingerprint")
            else None
        )
        resolved_dimension = (
            _read_uint64(manifest["dimension"])
            if manifest and manifest.get("dimension") is not None
            else None
        )
        manifest_model_name = (
            str(manifest["model_name"])
            if manifest and manifest.get("model_name")
            else None
        )
        resolved_prefix = model_prefix or (
            str(manifest["model_prefix"])
            if manifest and manifest.get("model_prefix")
            else None
        )

        resolved_model_path = model_path or config_model_path
        if resolved_model_path is None and manifest_model_name:
            default_models_dir = Path("~/.ledgermind/local/models").expanduser()
            resolved_model_path = default_models_dir / manifest_model_name

        if resolved_model_path is None:
            raise ValueError("model_path or manifest['model_path'] is required")

        path = Path(resolved_model_path).expanduser()
        if manifest_model_name and path.suffix == "":
            path = path / manifest_model_name

        if (
            path.suffix.lower() == ".gguf"
            and resolved_prefix is not None
            and not path.stem.startswith(resolved_prefix)
        ):
            # Prefix is an explicit naming hint, not a wildcard search key.
            raise ValueError("model_path does not match configured model prefix")

        self._model_path = path
        self._expected_dimension = resolved_dimension
        self._fingerprint = resolved_manifest_fingerprint
        self._model_builder = model_builder or _default_embedding_model_builder
        self._n_threads = n_threads
        self._gpu_layers = gpu_layers
        self._model: _EmbeddingModel | None = None
        self._dimension: int | None = resolved_dimension
        self._closed = False

    @property
    def fingerprint(self) -> str:
        if self._fingerprint is not None:
            return self._fingerprint

        self._fingerprint = self._compute_fingerprint(self._model_path)
        return self._fingerprint

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            model = self._ensure_model()
            if hasattr(model, "n_embd"):
                self._dimension = int(model.n_embd)
            elif hasattr(model, "embedding_size"):
                self._dimension = int(model.embedding_size)
            elif self._expected_dimension is not None:
                self._dimension = self._expected_dimension
            else:
                raise RuntimeError("vector dimension is unknown before first encoding")
        return self._dimension

    def encode(
        self,
        texts: Sequence[str],
        *,
        role: EmbeddingRole | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        if role is not None:
            raise VectorizerRoleError(
                "GGUF embedding backend does not support query/passage roles"
            )

        model = self._ensure_model()

        vectors: list[list[float]] = []
        for text in texts:
            try:
                raw = model.create_embedding(text, n_threads=self._n_threads)
            except TypeError:
                raw = model.create_embedding(text)
            vector = _extract_embedding(raw)
            if not vector:
                raise ValueError("empty embedding")
            expected_dimension = self._dimension
            if expected_dimension is None:
                expected_dimension = len(vector)
                self._dimension = expected_dimension
            if len(vector) != expected_dimension:
                raise ValueError("partial embedding result returned by model")
            vectors.append(vector)

        if len(vectors) != len(texts):
            raise ValueError("partial embedding result returned by model")

        return vectors

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._model is not None:
            self._model.close()
            self._model = None

    def _ensure_model(self) -> _EmbeddingModel:
        if self._model is None:
            self._closed = False
            self._model = self._model_builder(
                str(self._model_path),
                self._n_threads,
                self._gpu_layers,
            )
        return self._model

    def _compute_fingerprint(self, path: Path) -> str:
        if not path.is_file():
            return str(path)

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"
