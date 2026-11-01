"""OpenAI-compatible embedding vectorizer for the Local task boundary."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from ledgermind_local.installer.profiles.embedding_api import (
    OpenAICompatibleEmbeddingProvider,
)

from .vectorizer import EmbeddingRole, Vectorizer

MAX_EMBEDDING_BATCH_CHARS = 500_000


class OpenAIEmbeddingVectorizer(Vectorizer):
    """Adapt the installer API provider to Local's vectorizer protocol."""

    def __init__(
        self,
        *,
        endpoint: str,
        token: str,
        model: str,
        dimensions: int,
        batch_size: int,
        timeout_seconds: float,
        max_concurrency: int = 1,
        priority: Literal["interactive", "background"] | None = None,
        max_batch_chars: int = MAX_EMBEDDING_BATCH_CHARS,
    ) -> None:
        if max_batch_chars < 1:
            raise ValueError("max_batch_chars must be positive")
        self._max_batch_chars = int(max_batch_chars)
        self._provider = OpenAICompatibleEmbeddingProvider(
            endpoint=endpoint,
            token=token,
            model=model,
            dimensions=dimensions,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            timeout_seconds=timeout_seconds,
            priority=priority,
        )
        self._model = model
        self._dimension = dimensions

    @property
    def fingerprint(self) -> str:
        return f"api:{self._model}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(
        self,
        texts: Sequence[str],
        *,
        role: EmbeddingRole | None = None,
    ) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch_size = self._provider.batch_size
        batch: list[str] = []
        batch_chars = 0
        for text in texts:
            if batch and (
                len(batch) >= batch_size
                or batch_chars + len(text) > self._max_batch_chars
            ):
                vectors.extend(
                    [list(vector) for vector in self._provider.embed(batch, role=role)]
                )
                batch = []
                batch_chars = 0
            batch.append(text)
            batch_chars += len(text)
        if batch:
            vectors.extend(
                [list(vector) for vector in self._provider.embed(batch, role=role)]
            )
        return vectors

    def set_telemetry_context(
        self,
        *,
        operation: str,
        profile_fingerprint: str,
        operation_item_counts: dict[str, int] | None = None,
    ) -> None:
        """Attach the semantic batch label to the next real HTTP request."""

        self._provider.set_telemetry_context(
            operation=operation,
            profile_fingerprint=profile_fingerprint,
            operation_item_counts=operation_item_counts,
        )

    def close(self) -> None:
        self._provider.close()


__all__ = ["OpenAIEmbeddingVectorizer"]
