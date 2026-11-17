"""Configuration shared by non-Hermes lifecycle adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ...runtime.spool import (
    DEFAULT_RETRYABLE_FAILED_MAX_AGE_SECONDS,
    DEFAULT_RETRYABLE_FAILED_MAX_ATTEMPTS,
)


@dataclass(frozen=True, slots=True)
class LifecycleConfig:
    target: str
    endpoint: str
    token_file: str
    memory_space_id: str
    source_instance_id: str
    profile_id: str
    spool_dir: str
    runtime_command: str
    runtime_state_file: str | None = None
    config_file: str | None = None
    enabled: bool = True
    context_limit: int = 5
    retrieval_schema_version: int = 5
    request_timeout_seconds: float = 5.0
    heartbeat_seconds: float = 10.0
    adapter_version: str = "lifecycle-python/0.1.0"
    allow_remote: bool = False
    managed_runtime: bool = False
    model_residency_mode: Literal["session", "idle", "always_on"] = "idle"
    session_safety_ttl_seconds: float = 3_600.0
    spool_max_bytes: int = 50_000_000
    spool_max_files: int = 1_000
    max_round_payload_bytes: int = 5_000_000
    retryable_failed_max_attempts: int = DEFAULT_RETRYABLE_FAILED_MAX_ATTEMPTS
    retryable_failed_max_age_seconds: float = DEFAULT_RETRYABLE_FAILED_MAX_AGE_SECONDS


_REQUIRED = (
    "target",
    "endpoint",
    "memory_space_id",
    "source_instance_id",
    "profile_id",
    "spool_dir",
    "runtime_command",
)
_SUPPORTED_TARGETS = frozenset({"codex", "claude-code", "opencode", "openclaw"})


def load_lifecycle_config(path: str | Path) -> LifecycleConfig:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("integration config must be a JSON object")
    for key in _REQUIRED:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(f"integration config requires {key}")
    if payload["target"] not in _SUPPORTED_TARGETS:
        raise ValueError(f"unsupported integration target: {payload['target']}")
    residency_mode = str(payload.get("model_residency_mode", "idle"))
    if residency_mode not in {"session", "idle", "always_on"}:
        raise ValueError("integration config has invalid model_residency_mode")
    retrieval_schema_version = payload.get("retrieval_schema_version", 5)
    if (
        not isinstance(retrieval_schema_version, int)
        or isinstance(retrieval_schema_version, bool)
        or retrieval_schema_version not in {2, 4, 5}
    ):
        raise ValueError("retrieval_schema_version must be 2, 4 or 5")
    return LifecycleConfig(
        target=str(payload["target"]),
        endpoint=str(payload["endpoint"]).rstrip("/"),
        token_file=str(payload.get("token_file", "")),
        memory_space_id=str(payload["memory_space_id"]),
        source_instance_id=str(payload["source_instance_id"]),
        profile_id=str(payload["profile_id"]),
        spool_dir=str(payload["spool_dir"]),
        runtime_command=str(payload["runtime_command"]),
        runtime_state_file=(
            str(payload["runtime_state_file"])
            if isinstance(payload.get("runtime_state_file"), str)
            else None
        ),
        config_file=str(Path(path).expanduser().absolute()),
        enabled=bool(payload.get("enabled", True)),
        context_limit=max(int(payload.get("context_limit", 5)), 1),
        retrieval_schema_version=retrieval_schema_version,
        request_timeout_seconds=max(float(payload.get("request_timeout_seconds", 5.0)), 0.1),
        heartbeat_seconds=max(float(payload.get("heartbeat_seconds", 10.0)), 0.1),
        adapter_version=str(payload.get("adapter_version", "lifecycle-python/0.1.0")),
        allow_remote=bool(payload.get("allow_remote", False)),
        managed_runtime=bool(payload.get("managed_runtime", False)),
        model_residency_mode=cast(
            Literal["session", "idle", "always_on"],
            residency_mode,
        ),
        session_safety_ttl_seconds=max(
            float(payload.get("session_safety_ttl_seconds", 3_600.0)), 1.0
        ),
        spool_max_bytes=max(int(payload.get("spool_max_bytes", 50_000_000)), 1),
        spool_max_files=max(int(payload.get("spool_max_files", 1_000)), 1),
        max_round_payload_bytes=max(int(payload.get("max_round_payload_bytes", 5_000_000)), 1),
        retryable_failed_max_attempts=max(
            int(
                payload.get(
                    "retryable_failed_max_attempts", DEFAULT_RETRYABLE_FAILED_MAX_ATTEMPTS
                )
            ),
            1,
        ),
        retryable_failed_max_age_seconds=max(
            float(
                payload.get(
                    "retryable_failed_max_age_seconds",
                    DEFAULT_RETRYABLE_FAILED_MAX_AGE_SECONDS,
                )
            ),
            1.0,
        ),
    )


__all__ = ["LifecycleConfig", "load_lifecycle_config"]
