"""Installer status operation."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ledgermind_local.runtime.supervisor import RuntimeSupervisor

from ..paths import InstallerPaths
from .integrations import integration_status

_SUCCESS_STAGES = ("knowledge_resolution_completed", "no_semantic_candidates")
_FAILURE_STAGES = (
    "failed",
    "execution_semantic_failed",
    "knowledge_resolution_failed",
)


def _read_local_paths(paths: InstallerPaths) -> tuple[Path, Path] | None:
    local_config = paths.config_dir / "local-config.json"
    try:
        payload = json.loads(local_config.read_text(encoding="utf-8"))
        return (
            Path(payload["knowledge_database_path"]),
            Path(payload["rounds_database_path"]),
        )
    except (OSError, KeyError, TypeError, ValueError):
        return None


def _readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def memory_health(*, paths: InstallerPaths) -> dict[str, Any]:
    """Return durable pipeline progress without waking or mutating the runtime."""

    database_paths = _read_local_paths(paths)
    if database_paths is None:
        return {"status": "not_available", "reason": "local_config_unavailable"}
    knowledge_path, rounds_path = database_paths
    if not knowledge_path.is_file() or not rounds_path.is_file():
        return {"status": "not_available", "reason": "database_unavailable"}

    try:
        with closing(_readonly(knowledge_path)) as core:
            latest_success = core.execute(
                "SELECT MAX(updated_at) FROM semantic_round_batches "
                "WHERE stage IN (?, ?)",
                _SUCCESS_STAGES,
            ).fetchone()[0]
            latest_materialized = core.execute(
                "SELECT MAX(created_at) FROM knowledge_values"
            ).fetchone()[0]
            if latest_success is None:
                failed_since_success = core.execute(
                    "SELECT COUNT(*) FROM semantic_round_batches "
                    "WHERE stage IN (?, ?, ?)",
                    _FAILURE_STAGES,
                ).fetchone()[0]
            else:
                failed_since_success = core.execute(
                    "SELECT COUNT(*) FROM semantic_round_batches "
                    "WHERE stage IN (?, ?, ?) AND updated_at > ?",
                    (*_FAILURE_STAGES, latest_success),
                ).fetchone()[0]
            latest_failure = core.execute(
                "SELECT COALESCE(s.last_error_code, b.last_error_code, "
                "b.execution_error_code, b.object_resolution_error_code, "
                "b.embedding_error_code), b.updated_at "
                "FROM semantic_round_batches b "
                "LEFT JOIN operational_round_states s USING (raw_round_id) "
                "WHERE b.stage IN (?, ?, ?) "
                "ORDER BY b.updated_at DESC LIMIT 1",
                _FAILURE_STAGES,
            ).fetchone()
        with closing(_readonly(rounds_path)) as local:
            normalization_rejections = local.execute(
                "SELECT COUNT(*) FROM core_commands "
                "WHERE status = 'rejected' AND "
                "LOWER(COALESCE(last_error_detail, '')) LIKE '%normalized%budget%'"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        return {
            "status": "not_available",
            "reason": "database_query_failed",
            "error": str(exc),
        }

    degraded = int(failed_since_success) > 0 or int(normalization_rejections) > 0
    return {
        "status": "degraded" if degraded else "healthy",
        "last_successful_pipeline_at": latest_success,
        "last_materialized_at": latest_materialized,
        "failed_batches_since_last_success": int(failed_since_success),
        "normalization_rejections": int(normalization_rejections),
        "latest_failure": (
            {"error_code": latest_failure[0], "at": latest_failure[1]}
            if latest_failure is not None
            else None
        ),
    }


def status(*, paths: InstallerPaths) -> dict[str, Any]:
    current = str(paths.current_link.resolve()) if paths.current_link.exists() else None
    config_exists = paths.config_file.is_file()
    runtime = RuntimeSupervisor(paths).status()
    integrations: dict[str, Any] = {"status": "not_configured", "integrations": {}}
    if config_exists:
        integrations = integration_status(paths=paths)
        active_leases = runtime.get("active_leases", [])
        if not isinstance(active_leases, list):
            active_leases = []
        active_clients = {
            str(item.get("client")) for item in active_leases if isinstance(item, dict)
        }
        for target_id, item in integrations["integrations"].items():
            item["active"] = target_id in active_clients
    return {
        "installed": bool(current and config_exists),
        "current": current,
        "config": str(paths.config_file),
        "config_exists": config_exists,
        "runtime": runtime,
        "memory_health": memory_health(paths=paths),
        "integrations": integrations["integrations"],
    }


__all__ = ["memory_health", "status"]
