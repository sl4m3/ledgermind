"""Catalog of embedding runtimes shipped inside platform bundles."""

from __future__ import annotations

from typing import Any


def runtime_for(entry: dict[str, Any], device: str) -> dict[str, Any]:
    runtime_id = str(entry.get("runtime_id", "")).strip()
    if not runtime_id:
        raise ValueError("embedding catalog entry has no runtime_id")
    devices = entry.get("devices", [])
    if device not in devices:
        raise ValueError(f"runtime {runtime_id} is not approved for {device}")
    return {
        "runtime_id": runtime_id,
        "device": device,
        "compatibility": dict(entry.get("runtime_compatibility", {})),
    }


__all__ = ["runtime_for"]
