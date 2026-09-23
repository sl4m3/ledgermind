"""Local technical embedding backend boundary."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol, TypeAlias


EmbeddingRole: TypeAlias = Literal["query", "passage"]


class VectorizerRoleError(RuntimeError):
    """The backend cannot honor the requested query/passage role."""


class Vectorizer(Protocol):
    """Protocol implemented by Local embedding backends."""

    @property
    def fingerprint(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def encode(
        self,
        texts: Sequence[str],
        *,
        role: EmbeddingRole | None = None,
    ) -> Sequence[Sequence[float]]: ...

    def close(self) -> None: ...


__all__ = ["EmbeddingRole", "Vectorizer", "VectorizerRoleError"]
