"""Idle shutdown policy."""

from __future__ import annotations

import time


def should_shutdown(
    *,
    active_leases: int,
    leased_tasks: int = 0,
    pending_writes: int = 0,
    last_release_at: float | None,
    idle_grace_seconds: float,
    now: float | None = None,
) -> bool:
    if active_leases or leased_tasks or pending_writes:
        return False
    if last_release_at is None:
        return False
    return (time.time() if now is None else now) - last_release_at >= max(
        idle_grace_seconds, 0.0
    )


__all__ = ["should_shutdown"]
