"""Resolve the current local API address without trusting a foreign listener."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse


def default_runtime_state_file() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    root = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return root / "ledgermind" / "runtime" / "state.json"


def runtime_state_running(state_file: str | None = None) -> bool:
    path = Path(state_file).expanduser() if state_file else default_runtime_state_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("running") is True


def resolve_runtime_endpoint(configured: str, state_file: str | None = None) -> str:
    """Use only a loopback endpoint recorded by this installation's supervisor."""

    parsed_configured = urlparse(configured)
    if parsed_configured.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return configured
    if state_file is None and parsed_configured.port != 8765:
        # An explicit local test or custom service endpoint is authoritative.
        return configured
    path = Path(state_file).expanduser() if state_file else default_runtime_state_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return configured
    if not isinstance(payload, dict):
        return configured
    candidate = payload.get("preferred_endpoint") or payload.get("endpoint")
    if not isinstance(candidate, str):
        return configured
    parsed = urlparse(candidate)
    try:
        valid_port = parsed.port is not None
    except ValueError:
        return configured
    if (
        parsed.scheme != parsed_configured.scheme
        or parsed.hostname != parsed_configured.hostname
        or not valid_port
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
    ):
        return configured
    return candidate.rstrip("/")


__all__ = [
    "default_runtime_state_file",
    "resolve_runtime_endpoint",
    "runtime_state_running",
]
