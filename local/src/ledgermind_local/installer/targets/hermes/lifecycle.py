"""Hermes lifecycle environment contract for the installed adapter."""

from __future__ import annotations

from typing import Any


def lifecycle_contract(
    *,
    endpoint: str,
    lease_ttl_seconds: float,
    heartbeat_seconds: float,
    model_residency_mode: str = "idle",
    session_safety_ttl_seconds: float = 3_600.0,
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "lease_ttl_seconds": lease_ttl_seconds,
        "heartbeat_seconds": heartbeat_seconds,
        "model_residency_mode": model_residency_mode,
        "session_safety_ttl_seconds": session_safety_ttl_seconds,
        "acquire_before_context": True,
        "release_on_shutdown": True,
        "ttl_cleans_crash": True,
    }


__all__ = ["lifecycle_contract"]
