"""Embedding batch/concurrency presets."""

from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, int]] = {
    "conservative": {"batch_size": 8, "concurrency": 1},
    "balanced": {"batch_size": 32, "concurrency": 1},
    "throughput": {"batch_size": 128, "concurrency": 4},
}


def resolve_preset(
    name: str, *, batch_size: int | None = None, concurrency: int | None = None
) -> dict[str, Any]:
    if name == "custom":
        if batch_size is None or concurrency is None:
            raise ValueError("custom preset requires batch_size and concurrency")
        return {"batch_size": int(batch_size), "concurrency": int(concurrency)}
    try:
        values = dict(PRESETS[name])
    except KeyError as exc:
        raise ValueError(f"unknown embedding preset: {name}") from exc
    if batch_size is not None:
        values["batch_size"] = int(batch_size)
    if concurrency is not None:
        values["concurrency"] = int(concurrency)
    return values


__all__ = ["PRESETS", "resolve_preset"]
