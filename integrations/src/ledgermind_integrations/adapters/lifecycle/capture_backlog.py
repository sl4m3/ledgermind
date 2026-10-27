"""Durable completed-turn handoff, independent of transport queue capacity."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import LifecycleConfig


def backlog_dir(config: LifecycleConfig) -> Path:
    return Path(config.spool_dir).expanduser() / "completed-capture"


def _identity(session_id: str, state: Mapping[str, Any]) -> str:
    return hashlib.sha256(f"{session_id}:{state['round_id']}".encode()).hexdigest()


def _fingerprint(state: Mapping[str, Any]) -> str:
    evidence = {key: value for key, value in state.items()
                if key != "completed_at" and not key.startswith("runtime_lease")}
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def capture_was_enqueued(config: LifecycleConfig, session_id: str, state: Mapping[str, Any]) -> bool:
    path = Path(config.spool_dir) / "capture-receipts" / f"{_identity(session_id, state)}.json"
    if not path.exists():
        return False
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("evidence_sha256") != _fingerprint(state):
        raise ValueError("capture receipt conflicts with current evidence")
    return True


def record_capture_receipt(
    config: LifecycleConfig, session_id: str, state: Mapping[str, Any], digest: str
) -> None:
    root = Path(config.spool_dir) / "capture-receipts"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / f"{_identity(session_id, state)}.json"
    if path.exists():
        capture_was_enqueued(config, session_id, state)
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1, "payload_digest": digest,
                       "evidence_sha256": _fingerprint(state)}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        sync_directory(root)
    finally:
        temporary.unlink(missing_ok=True)


def persist_capture(
    config: LifecycleConfig, session_id: str, state: Mapping[str, Any], completed_at: str
) -> tuple[Path, dict[str, Any]]:
    """Commit a private snapshot before allowing active capture to be cleared."""
    root = backlog_dir(config)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    path = root / f"{_identity(session_id, state)}.json"
    snapshot = json.loads(json.dumps(dict(state), ensure_ascii=False))
    snapshot.pop("runtime_lease_id", None)
    capture = {"schema_version": 1, "session_id": session_id, "state": snapshot}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        prior = dict(existing["state"])
        prior.pop("completed_at", None)
        comparable = dict(snapshot)
        comparable.pop("completed_at", None)
        if prior != comparable or existing.get("session_id") != session_id:
            raise ValueError("completed capture identity conflicts with existing evidence")
        return path, existing
    snapshot["completed_at"] = completed_at
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(capture, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        sync_directory(root)
    finally:
        temporary.unlink(missing_ok=True)
    return path, capture


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def complete_capture(path: Path) -> None:
    path.unlink(missing_ok=True)
    sync_directory(path.parent)


def pending_captures(config: LifecycleConfig) -> list[Path]:
    return sorted(backlog_dir(config).glob("*.json"))
