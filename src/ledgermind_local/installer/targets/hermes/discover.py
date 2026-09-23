"""Hermes installation discovery without requiring Hermes as a Python import."""

from __future__ import annotations

import os
from pathlib import Path

from ..base import TargetDiscovery


def discover_hermes() -> TargetDiscovery:
    candidates: list[Path] = []
    for name in ("HERMES_HOME", "HERMES_CONFIG_HOME"):
        value = os.environ.get(name, "").strip()
        if value:
            candidates.append(Path(value).expanduser())
    candidates.append(Path.home() / ".hermes")
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.absolute()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_dir():
            config_dir = candidate / "config"
            if not config_dir.exists() and (candidate / "config.json").exists():
                config_dir = candidate
            return TargetDiscovery(
                "hermes",
                "Hermes",
                True,
                home=candidate,
                config_dir=config_dir,
                detail="Hermes home discovered",
            )
    return TargetDiscovery(
        "hermes",
        "Hermes",
        False,
        detail="Hermes home was not found; set HERMES_HOME before install",
    )


__all__ = ["discover_hermes"]
