"""Hermes hook registration metadata."""

from __future__ import annotations

from typing import Any

from .verify import REQUIRED_HOOKS


def hook_registration() -> dict[str, Any]:
    return {
        "hooks": sorted(REQUIRED_HOOKS),
        "lifecycle": {
            "before_first_memory_request": "runtime.acquire",
            "active_session": "runtime.heartbeat",
            "session_shutdown": "runtime.release",
            "crash_recovery": "lease.ttl",
        },
    }


__all__ = ["hook_registration"]
