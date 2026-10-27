"""Approved embedding model catalog."""

from __future__ import annotations

from typing import Any


class EmbeddingCatalog:
    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._entries = {
            str(entry.get("id")): dict(entry) for entry in entries if entry.get("id")
        }

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def get(self, catalog_id: str) -> dict[str, Any]:
        try:
            return dict(self._entries[catalog_id])
        except KeyError as exc:
            raise KeyError(f"unknown approved embedding model: {catalog_id}") from exc

    def require_device(self, catalog_id: str, device: str) -> dict[str, Any]:
        entry = self.get(catalog_id)
        devices = entry.get("devices")
        if not isinstance(devices, list) or device not in devices:
            raise ValueError(f"embedding model {catalog_id} does not support {device}")
        return entry


__all__ = ["EmbeddingCatalog"]
