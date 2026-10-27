"""Validation and device selection for signed local embedding assets."""

from __future__ import annotations

from typing import Any

from ..hardware import Device, choose_device
from ..models import LocalEmbeddingConfig


def build_local_embedding_plan(
    config: LocalEmbeddingConfig,
    catalog_entry: dict[str, Any],
) -> dict[str, Any]:
    if catalog_entry.get("id") != config.catalog_id:
        raise ValueError("local embedding catalog entry does not match config")
    devices = {str(value) for value in catalog_entry.get("devices", [])}
    if not devices:
        raise ValueError("signed local embedding catalog entry has no devices")
    selected: Device = choose_device(config.device, supported=devices)
    if selected.kind not in devices:
        raise ValueError(
            f"signed model does not support selected device: {selected.kind}"
        )
    dimensions = int(catalog_entry.get("dimensions", 0))
    runtime_id = str(catalog_entry.get("runtime_id", "")).strip()
    if dimensions <= 0:
        raise ValueError("signed local embedding catalog entry has no dimensions")
    if not runtime_id:
        raise ValueError("signed local embedding catalog entry has no runtime id")
    return {
        "catalog_id": config.catalog_id,
        "device": selected.kind,
        "device_name": selected.name,
        "model_path": config.model_path or config.model_storage_path,
        "batch_size": config.batch_size,
        "concurrency": config.concurrency,
        "threads": config.threads,
        "gpu_allocation": config.gpu_allocation,
        "auto_start": config.auto_start,
        "dimensions": dimensions,
        "runtime_id": runtime_id,
    }


__all__ = ["build_local_embedding_plan"]
