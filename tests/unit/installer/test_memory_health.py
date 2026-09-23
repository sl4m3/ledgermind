from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path

import pytest

from ledgermind_local.installer.models import (
    EmbeddingApiConfig,
    EmbeddingConfig,
    GenerationConfig,
    InstallerConfig,
)
from ledgermind_local.installer.operations.status import memory_health
from ledgermind_local.installer.paths import InstallerPaths


def _databases(paths: InstallerPaths) -> tuple[Path, Path]:
    core = paths.memory_data_dir / "core" / "knowledge.db"
    local = paths.memory_data_dir / "rounds.db"
    core.parent.mkdir(parents=True)
    local.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(core) as connection:
        connection.executescript(
            """
            CREATE TABLE semantic_round_batches (
                raw_round_id TEXT PRIMARY KEY, stage TEXT, updated_at TEXT,
                last_error_code TEXT, execution_error_code TEXT,
                object_resolution_error_code TEXT, embedding_error_code TEXT
            );
            CREATE TABLE operational_round_states (
                raw_round_id TEXT PRIMARY KEY, last_error_code TEXT
            );
            CREATE TABLE knowledge_values (created_at TEXT);
            """
        )
    with sqlite3.connect(local) as connection:
        connection.executescript(
            """
            CREATE TABLE core_commands (
                status TEXT, last_error_detail TEXT
            );
            """
        )
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    (paths.config_dir / "local-config.json").write_text(
        json.dumps(
            {
                "knowledge_database_path": str(core),
                "rounds_database_path": str(local),
            }
        ),
        encoding="utf-8",
    )
    return core, local


def test_memory_health_reports_failures_after_last_success(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    core, local = _databases(paths)
    with sqlite3.connect(core) as connection:
        connection.execute(
            "INSERT INTO semantic_round_batches(raw_round_id, stage, updated_at, last_error_code) "
            "VALUES (?, ?, ?, ?)",
            (
                "ok",
                "knowledge_resolution_completed",
                "2026-01-01T00:00:00Z",
                None,
            ),
        )
        connection.execute(
            "INSERT INTO semantic_round_batches(raw_round_id, stage, updated_at, last_error_code) "
            "VALUES (?, ?, ?, ?)",
            ("bad", "failed", "2026-01-01T00:01:00Z", "provider_invalid_request"),
        )
        connection.execute(
            "INSERT INTO operational_round_states VALUES (?, ?)",
            ("bad", "provider_invalid_request"),
        )
        connection.execute(
            "INSERT INTO knowledge_values VALUES (?)",
            ("2026-01-01T00:00:30Z",),
        )
    with sqlite3.connect(local) as connection:
        connection.execute(
            "INSERT INTO core_commands VALUES (?, ?)",
            ("rejected", "normalized payload budget exceeded"),
        )

    result = memory_health(paths=paths)

    assert result == {
        "status": "degraded",
        "last_successful_pipeline_at": "2026-01-01T00:00:00Z",
        "last_materialized_at": "2026-01-01T00:00:30Z",
        "failed_batches_since_last_success": 1,
        "normalization_rejections": 1,
        "latest_failure": {
            "error_code": "provider_invalid_request",
            "at": "2026-01-01T00:01:00Z",
        },
    }


def test_memory_health_is_read_only_and_healthy(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    core, _ = _databases(paths)
    with sqlite3.connect(core) as connection:
        connection.execute(
            "INSERT INTO semantic_round_batches(raw_round_id, stage, updated_at, last_error_code) "
            "VALUES (?, ?, ?, ?)",
            ("ok", "no_semantic_candidates", "2026-01-01T00:00:00Z", None),
        )

    assert memory_health(paths=paths)["status"] == "healthy"


def test_memory_health_reports_knowledge_resolution_failure(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    core, _ = _databases(paths)
    with sqlite3.connect(core) as connection:
        connection.execute(
            "INSERT INTO semantic_round_batches(raw_round_id, stage, updated_at) "
            "VALUES (?, ?, ?)",
            ("ok", "knowledge_resolution_completed", "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO semantic_round_batches("
            "raw_round_id, stage, updated_at, object_resolution_error_code"
            ") VALUES (?, ?, ?, ?)",
            (
                "bad-kr",
                "knowledge_resolution_failed",
                "2026-01-01T00:01:00Z",
                "knowledge_resolution_contract_invalid",
            ),
        )
        connection.execute(
            "INSERT INTO operational_round_states VALUES (?, ?)",
            ("bad-kr", None),
        )

    result = memory_health(paths=paths)

    assert result["status"] == "degraded"
    assert result["failed_batches_since_last_success"] == 1
    assert result["latest_failure"] == {
        "error_code": "knowledge_resolution_contract_invalid",
        "at": "2026-01-01T00:01:00Z",
    }


def test_configure_rolls_back_credentials_and_profiles_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_module = importlib.import_module(
        "ledgermind_local.installer.operations.configure"
    )
    paths = InstallerPaths(home_override=tmp_path)
    paths.ensure()
    original = {
        paths.config_file: b'{"old":"config"}\n',
        paths.profiles_file: b'{"old":"profiles"}\n',
        paths.secrets_file: b'{"secrets":{"generation/openai":"old-key"}}\n',
    }
    for path, content in original.items():
        path.write_bytes(content)
        path.chmod(0o600)
    config = InstallerConfig(
        semantic_language="en",
        generation=GenerationConfig(
            endpoint="https://provider.example/v1",
            token="new-generation-key",
            model="generation-model",
            object_resolution_model="generation-model",
        ),
        embedding=EmbeddingConfig(
            mode="api",
            api=EmbeddingApiConfig(
                endpoint="https://provider.example/v1",
                token="new-embedding-key",
                model="embedding-model",
                dimensions=3,
            ),
        ),
    )

    def fail_profiles(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("profile persistence failed")

    monkeypatch.setattr(configure_module, "write_local_profiles", fail_profiles)

    with pytest.raises(RuntimeError, match="profile persistence failed"):
        configure_module.configure(config=config, paths=paths)

    assert {path: path.read_bytes() for path in original} == original
