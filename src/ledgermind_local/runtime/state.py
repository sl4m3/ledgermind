"""Durable, secret-free runtime state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def load_state(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {
            "schema_version": 1,
            "running": False,
            "endpoint": None,
            "processes": {},
            "active_leases": 0,
            "last_transition": None,
        }
    payload = json.loads(target.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, dict) else {}


def write_state(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
        os.chmod(target, 0o600)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


__all__ = ["load_state", "write_state"]
