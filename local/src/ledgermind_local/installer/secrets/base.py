"""Secret backend protocol."""

from __future__ import annotations

from typing import Protocol


class SecretBackend(Protocol):
    def available(self) -> bool: ...

    def get(self, key: str) -> str | None: ...

    def put(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> bool: ...


__all__ = ["SecretBackend"]
