"""Configuration for the standalone Hermes integration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast


@dataclass(frozen=True, slots=True)
class HermesConfig:
    endpoint: str
    token_file: str
    memory_space_id: str
    source_instance_id: str
    profile_id: str
    state_db_path: str
    spool_dir: str
    enabled: bool = True
    adapter_version: str = "hermes-python/0.1.0"
    source_schema_version: int = 1
    allow_remote: bool = False
    context_limit: int = 5
    context_timeout_seconds: float = 1.5
    request_timeout_seconds: float = 5.0
    worker_poll_seconds: float = 0.5
    max_pending_attempts: int = 3
    max_raw_round_bytes: int = 5_000_000
    max_spool_bytes: int = 50_000_000
    max_spool_files: int = 1_000
    inflight_ttl_seconds: float = 300.0
    runtime_endpoint: str | None = None
    runtime_command: str | None = None
    runtime_heartbeat_seconds: float = 10.0
    model_residency_mode: Literal["session", "idle", "always_on"] = "idle"
    session_safety_ttl_seconds: float = 3_600.0
    project_id: str | None = None
    repository_id: str | None = None
    task_id: str | None = None
    working_directory: str | None = None
    repository_root: str | None = None
    repository_mapping: dict[str, object] = field(default_factory=dict)


_REQUIRED = ("endpoint", "memory_space_id", "source_instance_id", "profile_id")


def load_config(path: str | Path) -> HermesConfig:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Hermes config must be a JSON object")
    for key in _REQUIRED:
        if not str(payload.get(key, "")).strip():
            raise ValueError(f"Hermes config requires {key}")
    residency_mode = str(payload.get("model_residency_mode", "idle"))
    if residency_mode not in {"session", "idle", "always_on"}:
        raise ValueError("Hermes config has invalid model_residency_mode")
    heartbeat_value = payload.get("heartbeat_seconds")
    if heartbeat_value is None:
        heartbeat_value = payload.get("runtime_heartbeat_seconds")
    if heartbeat_value is None:
        heartbeat_value = 10.0
    resolution = payload.get("resolution")
    resolution_mapping = resolution if isinstance(resolution, Mapping) else {}

    def optional_text(name: str) -> str | None:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            value = resolution_mapping.get(name)
        return value.strip() if isinstance(value, str) and value.strip() else None

    raw_repository_mapping = payload.get("repository_mapping")
    if not isinstance(raw_repository_mapping, Mapping):
        raw_repository_mapping = resolution_mapping.get("repository_mapping", {})
    if not isinstance(raw_repository_mapping, Mapping):
        raise TypeError("Hermes repository_mapping must be an object")
    return HermesConfig(
        enabled=bool(payload.get("enabled", True)),
        endpoint=str(payload["endpoint"]),
        token_file=str(payload.get("token_file", "~/.ledgermind/server.token")),
        memory_space_id=str(payload["memory_space_id"]),
        source_instance_id=str(payload["source_instance_id"]),
        profile_id=str(payload["profile_id"]),
        state_db_path=str(payload.get("state_db_path", "~/.hermes/state.db")),
        spool_dir=str(payload.get("spool_dir", "~/.ledgermind/hermes-spool")),
        adapter_version=str(payload.get("adapter_version", "hermes-python/0.1.0")),
        source_schema_version=int(payload.get("source_schema_version", 1)),
        allow_remote=bool(payload.get("allow_remote", False)),
        context_limit=max(int(payload.get("context_limit", 5)), 1),
        context_timeout_seconds=max(float(payload.get("context_timeout_seconds", 1.5)), 0.1),
        request_timeout_seconds=max(float(payload.get("request_timeout_seconds", 5.0)), 0.1),
        worker_poll_seconds=max(float(payload.get("worker_poll_seconds", 0.5)), 0.05),
        max_pending_attempts=max(int(payload.get("max_pending_attempts", 3)), 1),
        max_raw_round_bytes=max(int(payload.get("max_raw_round_bytes", 5_000_000)), 1),
        max_spool_bytes=max(
            int(payload.get(
                "max_spool_bytes",
                10_000_000_000 if payload.get("runtime_command") == "ledgermind-cloud" else 50_000_000,
            )), 1
        ),
        max_spool_files=max(
            int(payload.get(
                "max_spool_files",
                100_000 if payload.get("runtime_command") == "ledgermind-cloud" else 1_000,
            )), 1
        ),
        inflight_ttl_seconds=max(float(payload.get("inflight_ttl_seconds", 300.0)), 0.1),
        runtime_endpoint=(
            str(payload["runtime_endpoint"]).rstrip("/")
            if payload.get("runtime_endpoint")
            else None
        ),
        runtime_command=(
            str(payload["runtime_command"]) if payload.get("runtime_command") else None
        ),
        runtime_heartbeat_seconds=max(
            float(str(heartbeat_value)),
            0.1,
        ),
        model_residency_mode=cast(
            Literal["session", "idle", "always_on"],
            residency_mode,
        ),
        session_safety_ttl_seconds=max(
            float(payload.get("session_safety_ttl_seconds", 3_600.0)), 1.0
        ),
        project_id=optional_text("project_id"),
        repository_id=optional_text("repository_id"),
        task_id=optional_text("task_id"),
        working_directory=optional_text("working_directory"),
        repository_root=optional_text("repository_root"),
        repository_mapping=dict(raw_repository_mapping),
    )
