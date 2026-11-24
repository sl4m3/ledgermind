from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path

import pytest

from ledgermind_local.installer import cli
from ledgermind_local.installer.errors import ExitCode
from ledgermind_local.installer.operations.status import memory_health, status
from ledgermind_local.installer.paths import InstallerPaths


@pytest.mark.parametrize(
    ("argv", "expected_snippets"),
    [
        (["--help"], ["Common workflows:", "doctor", "status", "integrations", "runtime"]),
        (["install", "--help"], ["setup interface", "schema", "plan"]),
        (["install", "schema", "--help"], ["schema document to emit"]),
        (["install", "plan", "--help"], ["planned LedgerMind installation"]),
        (["configure", "--help"], ["--validate-providers"]),
        (["status", "--help"], ["read-only status", "memory pipeline health"]),
        (["doctor", "--help"], ["--no-smoke", "bubblewrap isolation"]),
        (["repair", "--help"], ["Re-synchronize local config"]),
        (["update", "--help"], ["--manifest", "--bundle"]),
        (["uninstall", "--help"], ["--purge-data", "--purge-config"]),
        (["integrations", "--help"], ["discover", "status", "connect", "enable"]),
        (["integrations", "discover", "--help"], ["Detect which supported agents"]),
        (["integrations", "status", "--help"], ["connection/verification/queue"]),
        (["integrations", "connect", "--help"], ["agent identifier to connect"]),
        (["export-config", "--help"], ["--include-secrets"]),
        (["import-config", "--help"], ["--delete-config-after-import"]),
        (["runtime", "--help"], ["acquire", "heartbeat", "release", "status", "stop"]),
        (["runtime", "status", "--help"], ["processes, and active leases"]),
        (["runtime", "stop", "--help"], ["--force"]),
    ],
)
def test_cli_help_includes_descriptions_and_options(
    argv: list[str],
    expected_snippets: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)

    assert exc.value.code == 0
    raw_help = capsys.readouterr().out
    assert "==SUPPRESS==" not in raw_help
    if argv == ["--help"]:
        assert "integration-hook" not in raw_help
    if argv == ["runtime", "--help"]:
        assert "_idle-reap" not in raw_help
    help_text = " ".join(raw_help.split())
    for snippet in expected_snippets:
        assert snippet in help_text


def _setup_status_databases(paths: InstallerPaths) -> tuple[Path, Path]:
    core = paths.memory_data_dir / "core" / "knowledge.db"
    local = paths.memory_data_dir / "rounds.db"
    core.parent.mkdir(parents=True, exist_ok=True)
    local.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(core) as conn:
        conn.executescript(
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
    with sqlite3.connect(local) as conn:
        conn.executescript(
            """
            CREATE TABLE core_commands (status TEXT, last_error_detail TEXT);
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


def test_status_operation_adds_memory_summary_without_changing_memory_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    core, _ = _setup_status_databases(paths)
    with sqlite3.connect(core) as conn:
        conn.execute(
            "INSERT INTO semantic_round_batches(raw_round_id, stage, updated_at) "
            "VALUES (?, ?, ?)",
            ("r1", "knowledge_resolution_completed", "2026-11-24T14:57:12.466653921Z"),
        )
        conn.execute(
            "INSERT INTO knowledge_values VALUES (?)",
            ("2026-11-24T14:57:12.466653921Z",),
        )

    class _FakeSupervisor:
        def __init__(self, _paths: InstallerPaths) -> None:
            pass

        def status(self) -> dict[str, object]:
            return {
                "running": False,
                "residency_mode": "idle",
                "endpoint": None,
                "preferred_endpoint": "http://127.0.0.1:8765",
                "endpoint_failover": False,
                "endpoint_conflict": False,
                "active_leases": [],
            }

    status_module = importlib.import_module("ledgermind_local.installer.operations.status")
    monkeypatch.setattr(
        status_module,
        "RuntimeSupervisor",
        _FakeSupervisor,
    )

    health_before = memory_health(paths=paths)
    report = status(paths=paths)

    assert set(health_before.keys()) == {
        "status",
        "last_successful_pipeline_at",
        "last_materialized_at",
        "failed_batches_since_last_success",
        "normalization_rejections",
        "latest_failure",
    }
    assert report["memory_summary"] == {
        "active_knowledge_values": 1,
        "processed_batches": 1,
    }


def test_emit_status_distinguishes_resolved_prior_error_from_active_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    healthy_result = cli._result(
        "status",
        payload={
            "installed": True,
            "current": "/home/user/.local/share/ledgermind/releases/bundle-a",
            "config": "/home/user/.config/ledgermind/config.json",
            "config_exists": True,
            "runtime": {
                "running": True,
                "residency_mode": "session",
                "endpoint": "http://127.0.0.1:8765",
                "endpoint_failover": False,
                "endpoint_conflict": False,
                "active_leases": [{"client": "codex", "session_id": "s1"}],
            },
            "integrations": {
                "codex": {
                    "connected": True,
                    "enabled": True,
                    "active": True,
                    "discovery": {"label": "Codex CLI"},
                    "verify": {"status": "passed"},
                },
                "hermes": {
                    "connected": False,
                    "enabled": False,
                    "discovery": {"label": "Hermes"},
                },
            },
            "memory_summary": {
                "active_knowledge_values": 4,
                "processed_batches": 2,
            },
            "memory_health": {
                "status": "healthy",
                "last_successful_pipeline_at": "2026-11-24T14:57:12.466653921Z",
                "last_materialized_at": "2026-11-24T14:57:12.466653921Z",
                "failed_batches_since_last_success": 0,
                "normalization_rejections": 0,
                "latest_failure": {
                    "error_code": "round_memory_preparation_invalid",
                    "at": "2026-11-24T14:56:00Z",
                },
            },
        },
    )

    assert cli._emit(healthy_result, json_output=False) == 0
    out = capsys.readouterr().out
    assert "Installation:" in out
    assert "Installed:    yes" in out
    assert "State:        running" in out
    assert "1 active (codex)" in out
    assert "Codex CLI (codex): enabled, verify=passed, active session" in out
    assert "Hermes (hermes)" not in out
    assert "4 stored value(s), 2 processed batch(es)" in out
    assert "Last success: 2026-11-24 14:57:12 UTC" in out
    assert (
        "Prior error:  round_memory_preparation_invalid at 2026-11-24 14:56:00 UTC "
        "(resolved by later success)"
    ) in out
    assert "Latest error:" not in out

    degraded_result = cli._result(
        "status",
        payload={
            "installed": True,
            "current": "/home/user/.local/share/ledgermind/releases/bundle-a",
            "config": "/home/user/.config/ledgermind/config.json",
            "config_exists": True,
            "memory_health": {
                "status": "degraded",
                "last_successful_pipeline_at": "2026-11-24T14:57:12Z",
                "failed_batches_since_last_success": 1,
                "normalization_rejections": 0,
                "latest_failure": {
                    "error_code": "provider_invalid_request",
                    "at": "2026-11-24T14:58:00Z",
                },
            },
        },
    )
    cli._emit(degraded_result, json_output=False)
    degraded_out = capsys.readouterr().out
    assert "Latest error: provider_invalid_request at 2026-11-24 14:58:00 UTC" in degraded_out


def test_emit_doctor_human_and_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    payload = {
        "status": "passed",
        "platform": "linux-x86_64",
        "delivery": {
            "current": "/home/user/.local/share/ledgermind/releases/bundle-a",
            "bundle_manifest": True,
            "core": True,
            "local": True,
            "installer": True,
            "signature": {"status": "passed"},
        },
        "configuration": {
            "schema": "passed",
            "permissions": "passed",
            "secret_store": "file-0600",
            "local_config": "passed",
            "profile_slots": "passed",
            "core_config": {
                "security_profile": "secure",
                "semantic_language": "ru",
                "generation_concurrency": 4,
                "embedding_max_concurrency": 2,
            },
        },
        "providers": {
            "generation": {
                "endpoint": "https://openrouter.ai/api",
                "model": "meta/muse-ember",
                "route": "google-vertex/global",
                "reasoning_effort": "minimal",
                "strict_structured_outputs": True,
            },
            "embedding": {
                "status": "passed",
                "endpoint": "https://openrouter.ai/api",
                "model": "nvidia/nemotron-3.5-embed-1b:free",
                "dimensions": 2048,
            },
            "resolution_decision": {
                "status": "passed",
                "backend": "jev",
                "model": "typesafe/jev",
                "latency_ms": 42,
            },
        },
        "runtime": {
            "running": False,
            "preferred_endpoint": "http://127.0.0.1:8765",
            "residency_mode": "session",
            "active_leases": [],
        },
        "smoke_test": {
            "status": "passed",
            "writes_user_memory": False,
        },
        "integrations": {
            "opencode": {
                "enabled": True,
                "discovery": {"label": "OpenCode", "detected": True},
                "adapter": {"status": "passed"},
            }
        },
    }
    result = cli._result("doctor", payload=payload)

    assert cli._emit(result, json_output=False) == 0
    human = capsys.readouterr().out
    assert "Delivery:" in human
    assert "Signature:     passed" in human
    assert "Secret store:  file-0600" in human
    assert "language=ru" in human
    assert "Generation:    passed (model=meta/muse-ember, route=google-vertex/global, reasoning=minimal" in human
    assert "Embeddings:    passed (model=nvidia/nemotron-3.5-embed-1b:free, dims=2048" in human
    assert "Decision:      passed (backend=jev, model=typesafe/jev, latency=42ms)" in human
    assert "Smoke test:    passed (isolated, no user memory modified)" in human
    assert "OpenCode (opencode): enabled, detected=yes, verify=passed" in human

    assert cli._emit(result, json_output=True) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["operation"] == "doctor"
    assert parsed["status"] == "success"
    assert parsed["steps"][0]["status"] == "passed"

    failing_result = cli._result(
        "doctor",
        payload={
            "status": "failed",
            "platform": "linux-x86_64",
            "delivery": {"current": "missing"},
            "configuration": {"schema": "missing", "permissions": "passed"},
            "providers": {"status": "failed", "error": "authentication failed"},
            "smoke_test": {"status": "skipped", "writes_user_memory": False},
        },
    )
    failing_result.fail(ExitCode.DOCTOR_FAILED, "doctor found failures")
    assert cli._emit(failing_result, json_output=False) == int(ExitCode.DOCTOR_FAILED)
    failed_io = capsys.readouterr()
    assert "Status:        failed (authentication failed)" in failed_io.out
    assert "doctor found failures" in failed_io.err


def test_emit_runtime_and_config_transfer_outputs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_res = cli._result(
        "runtime status",
        payload={
            "running": True,
            "residency_mode": "idle",
            "endpoint": "http://127.0.0.1:8765",
            "endpoint_failover": False,
            "endpoint_conflict": False,
            "active_leases": [
                {
                    "client": "opencode",
                    "session_id": "sess-9",
                    "lease_id": "lease-1",
                    "expires_at": "2026-11-24T15:05:00Z",
                }
            ],
            "processes": {"local": {"pid": 12345}},
        },
    )
    assert cli._emit(runtime_res, json_output=False) == 0
    runtime_out = capsys.readouterr().out
    assert "Runtime state:" in runtime_out
    assert "client=opencode, session=sess-9, lease=lease-1, expires=2026-11-24 15:05:00 UTC" in runtime_out
    assert "local (pid=12345)" in runtime_out

    stop_res = cli._result(
        "runtime stop",
        payload={"stopped": True, "processes": {"local": "stopped"}},
    )
    cli._emit(stop_res, json_output=False)
    assert "Stopped:       yes" in capsys.readouterr().out

    export_res = cli._result(
        "export-config",
        payload={"status": "passed", "out": "/tmp/cfg.json", "include_secrets": False},
    )
    cli._emit(export_res, json_output=False)
    export_out = capsys.readouterr().out
    assert "File:          /tmp/cfg.json" in export_out
    assert "Secrets:       excluded (refs only)" in export_out

    import_res = cli._result(
        "import-config",
        payload={
            "status": "passed",
            "config": {"config": "/tmp/dest.json"},
            "probes": {"generation": {}},
            "target_registered": True,
        },
    )
    cli._emit(import_res, json_output=False)
    import_out = capsys.readouterr().out
    assert "Config file:   /tmp/dest.json" in import_out
    assert "Probes run:    generation" in import_out
    assert "Target agents: marked for registration" in import_out

    plan_res = cli._result(
        "install plan",
        payload={
            "platform": "linux-x86_64",
            "memory_mode": "shared",
            "memory_data_path": "/tmp/data",
            "integrations": [{"id": "codex", "enabled": True}],
            "profiles": [{"profile_id": "gen"}],
            "runtime": {"residency_mode": "session"},
        },
    )
    cli._emit(plan_res, json_output=False)
    plan_out = capsys.readouterr().out
    assert "Install plan:" in plan_out
    assert "Agents:        codex(on)" in plan_out
    assert "Profiles:      1 planned" in plan_out

    schema_res = cli._result("install schema", payload={"title": "InstallerConfig", "type": "object"})
    cli._emit(schema_res, json_output=False)
    schema_out = capsys.readouterr().out
    assert '"title": "InstallerConfig"' in schema_out
