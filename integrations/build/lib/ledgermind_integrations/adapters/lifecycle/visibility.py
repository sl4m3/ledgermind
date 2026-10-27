"""Small durable, host-scoped ledger of memory assumed to remain in context.

The ledger contains identifiers and counters only, never injected knowledge text.
It deliberately distinguishes hook return from a host-confirmed model input.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..hermes.config import HermesConfig
from .config import LifecycleConfig

MAX_AGE_TOKENS = 200_000
VisibilityConfig = LifecycleConfig | HermesConfig


def _path(config: VisibilityConfig, session_id: str) -> Path:
    try:
        token_digest = hashlib.sha256(Path(config.token_file).expanduser().read_bytes()).hexdigest() if config.token_file else ""
    except OSError:
        token_digest = ""
    identity = (
        f"{config.endpoint}\0{config.source_instance_id}\0{config.target}\0"
        f"{config.memory_space_id}\0{session_id}\0{token_digest}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return Path(config.spool_dir).expanduser() / "visibility" / f"{digest}.json"


@contextmanager
def _ledger(config: VisibilityConfig, session_id: str) -> Iterator[dict]:
    path = _path(config, session_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    with path.with_suffix(".lock").open("a+b") as lock:
        os.chmod(path.with_suffix(".lock"), 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state = {}
            if not isinstance(state, dict):
                state = {}
            state.setdefault("schema_version", 1)
            state.setdefault("epoch", 0)
            state.setdefault("cursor", 0)
            state.setdefault("entries", {})
            state.setdefault("seen_events", [])
            yield state
            temp = path.with_suffix(f".{uuid4().hex}.tmp")
            temp.write_text(json.dumps(state, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            os.chmod(temp, 0o600)
            temp.replace(path)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def visible_ids(config: VisibilityConfig, session_id: str) -> list[str]:
    with _ledger(config, session_id) as state:
        cursor = int(state["cursor"])
        epoch = int(state["epoch"])
        entries = state["entries"]
        for value_id, entry in list(entries.items()):
            if not isinstance(entry, dict) or entry.get("epoch") != epoch or cursor - int(entry.get("cursor", 0)) >= MAX_AGE_TOKENS:
                entries.pop(value_id, None)
        if len(entries) > 4096:
            raise ValueError("visibility ledger exceeds the retrieval exclusion limit")
        return sorted(entries)


def diagnostics(config: VisibilityConfig, session_id: str) -> dict[str, int | str]:
    with _ledger(config, session_id) as state:
        cursor = int(state["cursor"])
        entries = state["entries"]
        ages = [cursor - int(entry.get("cursor", cursor)) for entry in entries.values() if isinstance(entry, dict)]
        return {
            "epoch": int(state["epoch"]),
            "estimated_new_content_tokens": cursor,
            "oldest_injection_age_estimate": max(ages, default=0),
            "visible_value_count": len(entries),
            "age_estimation": "approximate_utf8_bytes_divided_by_four",
        }


def note_content(config: VisibilityConfig, session_id: str, event_id: str, content: object) -> None:
    if not event_id or content is None:
        return
    rendered = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, sort_keys=True)
    with _ledger(config, session_id) as state:
        seen = state["seen_events"]
        if event_id in seen:
            return
        state["cursor"] += (len(rendered.encode("utf-8")) + 3) // 4
        seen.append(event_id)
        if len(seen) > 4096:
            del seen[: len(seen) - 4096]


def assume_hook_returned(
    config: VisibilityConfig, session_id: str, injection_id: str, value_ids: list[str]
) -> None:
    with _ledger(config, session_id) as state:
        for value_id in value_ids:
            if value_id and value_id not in state["entries"]:
                state["entries"][value_id] = {
                    "injection_id": injection_id,
                    "epoch": state["epoch"],
                    "cursor": state["cursor"],
                    "at": datetime.now(timezone.utc).isoformat(),
                    "stage": "hook_returned_assumed_visible",
                }


def advance_epoch(config: VisibilityConfig, session_id: str) -> None:
    with _ledger(config, session_id) as state:
        state["epoch"] += 1
        state["cursor"] = 0
        state["entries"] = {}
        state["seen_events"] = []


__all__ = ["MAX_AGE_TOKENS", "advance_epoch", "assume_hook_returned", "diagnostics", "note_content", "visible_ids"]
