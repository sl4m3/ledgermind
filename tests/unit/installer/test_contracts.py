from __future__ import annotations

import io
import json
import os
import stat
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ledgermind_local.cli import _build_runtime_supervisor
from ledgermind_local.config import EmbeddingConfig as LocalEmbeddingConfig
from ledgermind_local.config import LocalConfig
from ledgermind_local.inference.secrets import SecretStore
from ledgermind_local.installer import cli as installer_cli
from ledgermind_local.installer.cli import _emit, _result, _runtime
from ledgermind_local.installer.config_writer import (
    bind_existing_profiles_for_agent,
    load_installer_config,
    persist_generation_probe,
    select_secret_backend,
    write_installer_config,
    write_local_config,
    write_local_profiles,
)
from ledgermind_local.installer.embeddings.service import EmbeddingService
from ledgermind_local.installer.errors import SignatureVerificationError
from ledgermind_local.installer.models import (
    EmbeddingApiConfig,
    EmbeddingConfig,
    GenerationConfig,
    InstallerConfig,
)
from ledgermind_local.installer.models import (
    LocalEmbeddingConfig as InstallerLocalEmbeddingConfig,
)
from ledgermind_local.installer.paths import InstallerPaths
from ledgermind_local.installer.verify import verify_ed25519
from ledgermind_local.runtime.process import process_start_ticks
from ledgermind_local.runtime.supervisor import RuntimeSupervisor


def _config() -> InstallerConfig:
    return InstallerConfig(
        semantic_language="en",
        generation=GenerationConfig(
            endpoint="https://provider.example/v1",
            token="generation-secret",
            model="generation-model",
        ),
        embedding=EmbeddingConfig(
            mode="api",
            api=EmbeddingApiConfig(
                endpoint="https://provider.example/v1",
                token="embedding-secret",
                model="embedding-model",
                dimensions=3,
            ),
        ),
    )


def test_integration_hook_records_redacted_import_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "codex" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"prompt":"secret prompt"}'))

    def fail_import(_name: str):
        raise ModuleNotFoundError("missing lifecycle package")

    monkeypatch.setattr(installer_cli.importlib, "import_module", fail_import)

    exit_code = installer_cli.main(
        [
            "integration-hook",
            "--config",
            str(config_path),
            "--event",
            "UserPromptSubmit",
        ]
    )

    assert exit_code == 0
    diagnostic_path = config_path.parent / "hook-errors.jsonl"
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    assert diagnostic["event"] == "UserPromptSubmit"
    assert diagnostic["error_type"] == "ModuleNotFoundError"
    assert diagnostic["error"] == "missing lifecycle package"
    assert "secret prompt" not in diagnostic_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(diagnostic_path.stat().st_mode) == 0o600
    assert "UserPromptSubmit hook failed" in capsys.readouterr().err


def test_integrations_discover_human_output_lists_agents(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _result(
        "integrations discover",
        payload={
            "status": "passed",
            "integrations": {
                "codex": {
                    "label": "Codex CLI",
                    "detected": True,
                    "config_dir": "/tmp/codex",
                },
                "openclaw": {
                    "label": "OpenClaw",
                    "detected": False,
                    "detail": "OpenClaw was not found",
                },
            },
        },
    )

    assert _emit(result, json_output=False) == 0
    output = capsys.readouterr().out
    assert "Codex CLI (codex): found — /tmp/codex" in output
    assert "OpenClaw (openclaw): not found — OpenClaw was not found" in output


def test_integrations_status_human_output_lists_connection_state(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _result(
        "integrations status",
        payload={
            "status": "passed",
            "integrations": {
                "codex": {
                    "installed_agent": True,
                    "connected": True,
                    "enabled": True,
                    "active": False,
                    "discovery": {"label": "Codex CLI", "detected": True},
                    "verify": {
                        "status": "passed",
                        "activation_required": "Review hooks",
                    },
                }
            },
        },
    )

    assert _emit(result, json_output=False) == 0
    output = capsys.readouterr().out
    assert (
        "Codex CLI (codex): detected=yes, connected=yes, enabled=yes, "
        "verify=passed" in output
    )
    assert "active=" not in output
    assert "note: Review hooks" in output


def test_config_writer_uses_0600_file_fallback_and_strips_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    paths = InstallerPaths(home_override=tmp_path)
    write_installer_config(_config(), paths)

    loaded = load_installer_config(paths.config_file)
    assert loaded.generation.secret_ref == "generation-api"
    assert loaded.generation.token is None
    assert "generation-secret" not in paths.config_file.read_text(encoding="utf-8")
    assert stat.S_IMODE(paths.config_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(paths.secrets_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(paths.secrets_file.parent.stat().st_mode) == 0o700
    runtime_secrets = SecretStore(paths.secrets_file)
    assert runtime_secrets.get("generation-api") == "generation-secret"
    assert runtime_secrets.get("embedding-api") == "embedding-secret"
    server_token = paths.data_dir / "local" / "server.token"
    assert server_token.read_text(encoding="utf-8").strip()
    assert stat.S_IMODE(server_token.stat().st_mode) == 0o600
    assert "server.token" not in paths.config_file.read_text(encoding="utf-8")


def test_runtime_file_is_the_canonical_secret_store_even_with_dbus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LEDGERMIND_SECRET_BACKEND", raising=False)
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/stale-desktop-keyring")
    paths = InstallerPaths(home_override=tmp_path)

    backend = select_secret_backend(paths)

    assert backend.__class__.__name__ == "FileSecretStore"
    assert backend.path == paths.secrets_file


def test_update_style_config_write_preserves_provider_credentials_byte_for_byte(
    tmp_path: Path,
) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    write_installer_config(_config(), paths)
    before = paths.secrets_file.read_bytes()
    changed_tokens = _config().model_copy(
        update={
            "generation": _config().generation.model_copy(
                update={"token": "must-not-replace-generation"}
            ),
            "embedding": _config().embedding.model_copy(
                update={
                    "api": _config().embedding.api.model_copy(
                        update={"token": "must-not-replace-embedding"}
                    )
                }
            ),
        }
    )

    write_installer_config(
        changed_tokens,
        paths,
        preserve_provider_credentials=True,
    )

    assert paths.secrets_file.read_bytes() == before


def test_config_writer_preserves_existing_local_server_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    paths = InstallerPaths(home_override=tmp_path)
    token_file = paths.data_dir / "local" / "server.token"
    token_file.parent.mkdir(parents=True)
    token_file.write_text("stable-token\n", encoding="utf-8")

    write_installer_config(_config(), paths)

    assert token_file.read_text(encoding="utf-8") == "stable-token\n"
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_local_service_config_is_written_under_xdg_data(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    write_local_config(_config(), paths)

    service_config = paths.data_dir / "local" / "config.json"
    assert service_config.is_file()
    assert stat.S_IMODE(service_config.stat().st_mode) == 0o600


def test_installer_materializes_profiles_for_local_resolver(tmp_path: Path) -> None:
    from ledgermind_local.inference.profile_store import InferenceProfileStore
    from ledgermind_local.persistence import open_sqlite_connection

    paths = InstallerPaths(home_override=tmp_path)
    result = write_local_profiles(_config(), paths)
    connection = open_sqlite_connection(result["database"])
    try:
        store = InferenceProfileStore(connection)
        slots = store.list_slots("hermes-default")
        materialized = [store.get(profile_id) for profile_id in slots.values()]
    finally:
        connection.close()

    assert slots == {
        "background": "generation-background",
        "embedding": "embedding-default",
        "operational": "generation-operational",
        "object_resolution": "generation-object-resolution",
    }
    assert {profile.secret_ref for profile in materialized} == {
        "generation-api",
        "embedding-api",
    }
    assert all(
        profile.max_output_tokens >= 2_048
        for profile in materialized
        if profile.profile_id.startswith("generation-")
    )
    by_id = {profile.profile_id: profile for profile in materialized}
    assert all(
        profile.max_input_tokens == 64_000
        for profile in materialized
        if profile.profile_id.startswith("generation-")
    )
    assert by_id["generation-operational"].max_output_tokens == 6_144
    assert by_id["generation-object-resolution"].max_output_tokens == 2_048
    assert by_id["generation-background"].max_output_tokens == 2_048
    assert all(
        profile.structured_output_preference == "strict_json_schema"
        for profile in materialized
        if profile.profile_id.startswith("generation-")
    )


def test_connecting_agent_binds_only_missing_slots_without_rewriting_profiles(
    tmp_path: Path,
) -> None:
    from ledgermind_local.inference.profile_store import InferenceProfileStore
    from ledgermind_local.persistence import open_sqlite_connection

    paths = InstallerPaths(home_override=tmp_path)
    config = _config()
    result = write_local_profiles(config, paths)
    connection = open_sqlite_connection(result["database"])
    try:
        store = InferenceProfileStore(connection)
        original = store.get("generation-operational")
        assert original is not None
    finally:
        connection.close()

    connection = open_sqlite_connection(result["database"])
    try:
        connection.execute(
            "INSERT INTO memory_spaces (memory_space_id, source_client, created_at, updated_at) "
            "VALUES ('opencode-default', 'ledgermind-integrations', 'now', 'now')"
        )
        connection.commit()
    finally:
        connection.close()

    added = bind_existing_profiles_for_agent(config, paths, "opencode")
    assert set(added) == {"operational", "object_resolution", "background", "embedding"}
    assert bind_existing_profiles_for_agent(config, paths, "opencode") == {}
    connection = open_sqlite_connection(result["database"])
    try:
        store = InferenceProfileStore(connection)
        assert store.get("generation-operational") == original
        assert store.list_slots("opencode-default") == added
    finally:
        connection.close()


def test_installer_persists_verified_generation_capabilities(tmp_path: Path) -> None:
    from ledgermind_local.inference.profile_store import InferenceProfileStore
    from ledgermind_local.inference.profiles import generation_profile_fingerprint
    from ledgermind_local.persistence import open_sqlite_connection

    paths = InstallerPaths(home_override=tmp_path)
    config = _config()
    profile_metadata = write_local_profiles(config, paths)
    result = persist_generation_probe(
        config,
        paths,
        {
            "strict_structured_outputs": True,
            "probed_models": ["generation-model", "object-resolution-model"],
            "probe_contract_digest": "sha256:test",
        },
    )
    connection = open_sqlite_connection(profile_metadata["database"])
    try:
        store = InferenceProfileStore(connection)
        for profile_id in result["profile_ids"]:
            profile = store.get(profile_id)
            assert profile is not None
            capabilities = store.get_capabilities(profile_id)
            assert capabilities is not None
            assert capabilities.supports("strict_json_schema")
            assert capabilities.profile_fingerprint == generation_profile_fingerprint(
                profile
            )
            assert capabilities.expires_at is None
    finally:
        connection.close()


def test_installer_materializes_one_profile_space_for_shared_agent_memory(
    tmp_path: Path,
) -> None:
    from ledgermind_local.inference.profile_store import InferenceProfileStore
    from ledgermind_local.persistence import open_sqlite_connection

    paths = InstallerPaths(home_override=tmp_path)
    config = _config().model_copy(update={"memory_mode": "shared"})
    result = write_local_profiles(config, paths)
    connection = open_sqlite_connection(result["database"])
    try:
        store = InferenceProfileStore(connection)
        slots = store.list_slots("shared-default")
        spaces = connection.execute(
            "SELECT memory_space_id FROM memory_spaces ORDER BY memory_space_id"
        ).fetchall()
    finally:
        connection.close()

    assert result["memory_space_id"] == "shared-default"
    assert result["memory_space_ids"] == ["shared-default"]
    assert [row["memory_space_id"] for row in spaces] == ["shared-default"]
    assert slots == {
        "background": "generation-background",
        "embedding": "embedding-default",
        "operational": "generation-operational",
        "object_resolution": "generation-object-resolution",
    }


def test_ed25519_rejects_tampered_manifest() -> None:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    payload = b"signed manifest"
    verify_ed25519(payload, private.sign(payload), public)
    with pytest.raises(SignatureVerificationError):
        verify_ed25519(b"tampered", private.sign(payload), public)


def test_runtime_supports_multiple_leases_and_ttl_cleanup(
    tmp_path: Path,
) -> None:
    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        lease_ttl_seconds=0.1,
        idle_shutdown_seconds=0,
    )
    first = supervisor.acquire(client="hermes", session_id="one")
    second = supervisor.acquire(client="hermes", session_id="two")
    assert first["started"] is True
    assert second["started"] is False
    assert len(supervisor.status()["active_leases"]) == 2
    time.sleep(0.15)
    assert supervisor.status()["active_leases"] == []
    assert supervisor.status()["running"] is False


def test_runtime_reuses_lease_for_the_same_client_session(tmp_path: Path) -> None:
    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        lease_ttl_seconds=0.1,
        max_session_ttl_seconds=10.0,
        idle_shutdown_seconds=0,
    )
    first = supervisor.acquire(client="codex", session_id="thread-1", ttl_seconds=2.0)
    second = supervisor.acquire(client="codex", session_id="thread-1", ttl_seconds=2.0)
    try:
        assert second["lease_id"] == first["lease_id"]
        assert second["started"] is False
        assert len(supervisor.status()["active_leases"]) == 1
    finally:
        supervisor.stop(force=True)


def test_runtime_lease_bridge_does_not_mutate_process_ownership(
    tmp_path: Path,
) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    paths.ensure()
    original = {
        "running": True,
        "endpoint": "http://127.0.0.1:8765",
        "processes": {"local": {"pid": os.getpid(), "command": ["local"]}},
    }
    paths.runtime_state.write_text(json.dumps(original), encoding="utf-8")
    bridge = RuntimeSupervisor(
        paths,
        commands={},
        automatic_shutdown=False,
        process_owner=False,
    )

    first = bridge.acquire(client="codex", session_id="thread-1")
    second = bridge.acquire(client="codex", session_id="thread-1")
    state = json.loads(paths.runtime_state.read_text(encoding="utf-8"))

    assert first["lease_id"] == second["lease_id"]
    assert state["running"] is True
    assert state["processes"] == original["processes"]
    assert len(bridge.status()["active_leases"]) == 1
    bridge.heartbeat(str(first["lease_id"]))
    assert paths.runtime_state.read_text(encoding="utf-8") == json.dumps(original)
    bridge.release(str(first["lease_id"]))
    assert paths.runtime_state.read_text(encoding="utf-8") == json.dumps(original)


def test_runtime_recovers_live_processes_from_registry_without_respawning(
    tmp_path: Path,
) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    commands = {
        "local": ("/bin/sleep", "60"),
        "embedding": ("/bin/sleep", "60"),
    }
    original = RuntimeSupervisor(paths, commands=commands, automatic_shutdown=False)
    original.acquire(client="codex", session_id="first")
    initial = original.status()["processes"]
    assert set(initial) == set(commands)
    assert (paths.runtime_dir / "processes.json").is_file()
    paths.runtime_state.write_text(
        json.dumps({"running": False, "processes": {}}), encoding="utf-8"
    )

    recovered = RuntimeSupervisor(paths, commands=commands, automatic_shutdown=False)
    try:
        assert recovered.status()["running"] is True
        assert recovered.status()["processes"] == initial
        lease = recovered.acquire(client="codex", session_id="second")
        assert lease["started"] is False
        assert recovered.status()["processes"] == initial
    finally:
        recovered.stop(force=True)
    assert not (paths.runtime_dir / "processes.json").exists()
    assert recovered.status()["running"] is False


def test_runtime_rejects_recycled_pid_in_registry(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    paths.ensure()
    start_ticks = process_start_ticks(os.getpid())
    assert start_ticks is not None
    registry = paths.runtime_dir / "processes.json"
    registry.write_text(
        json.dumps(
            {"processes": {"local": {"pid": os.getpid(), "start_ticks": start_ticks + 1}}}
        ),
        encoding="utf-8",
    )
    supervisor = RuntimeSupervisor(
        paths, commands={"local": ("/bin/sleep", "60")}, automatic_shutdown=False
    )
    assert supervisor.status()["running"] is False
    assert not registry.exists()


def test_runtime_session_lease_uses_extended_safety_ttl(tmp_path: Path) -> None:
    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        lease_ttl_seconds=0.1,
        max_session_ttl_seconds=10.0,
        idle_shutdown_seconds=0,
    )
    lease = supervisor.acquire(client="codex", session_id="long-turn", ttl_seconds=2.0)
    try:
        time.sleep(0.15)
        active = supervisor.status()["active_leases"]
        assert len(active) == 1
        assert active[0]["lease_id"] == lease["lease_id"]
        assert active[0]["ttl_seconds"] == 2.0
    finally:
        supervisor.stop(force=True)


def test_runtime_always_on_ignores_idle_shutdown(tmp_path: Path) -> None:
    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        commands={"local": ("/bin/sleep", "60")},
        idle_shutdown_seconds=0,
        automatic_shutdown=False,
    )
    lease = supervisor.acquire(client="agent", session_id="always-on")
    try:
        supervisor.release(str(lease["lease_id"]))
        assert supervisor.watch_idle()["reason"] == "automatic_shutdown_disabled"
        assert supervisor.status()["running"] is True
    finally:
        supervisor.stop(force=True)


def test_runtime_enables_persistent_content_free_provider_telemetry(
    tmp_path: Path,
) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    report = tmp_path / "provider-telemetry-path.txt"
    probe = (
        "import os, pathlib; "
        f"pathlib.Path({str(report)!r}).write_text("
        "os.environ.get('LEDGERMIND_PROVIDER_TELEMETRY_PATH', ''), encoding='utf-8')"
    )
    supervisor = RuntimeSupervisor(
        paths,
        commands={"probe": (sys.executable, "-c", probe)},
        idle_shutdown_seconds=0,
    )

    try:
        supervisor.acquire(client="test", session_id="telemetry")
        deadline = time.monotonic() + 2
        while not report.exists() and time.monotonic() < deadline:
            time.sleep(0.01)

        assert report.read_text(encoding="utf-8") == str(
            paths.logs_dir / "provider-telemetry.jsonl"
        )
    finally:
        supervisor.stop(force=True)


def test_runtime_restarts_missing_process_while_a_lease_is_active(
    tmp_path: Path,
) -> None:
    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        commands={"local": ("/bin/sleep", "60")},
    )
    first = supervisor.acquire(client="agent", session_id="one")
    try:
        supervisor.stop(force=True)
        second = supervisor.acquire(client="agent", session_id="two")
        assert first["started"] is True
        assert second["started"] is True
        assert supervisor.status()["processes"]
    finally:
        supervisor.stop(force=True)


def test_runtime_does_not_start_or_restart_during_update(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    barrier = paths.runtime_dir / "update-in-progress"
    barrier.write_text("pid=123\n", encoding="utf-8")
    supervisor = RuntimeSupervisor(
        paths,
        commands={"local": ("/bin/sleep", "60")},
    )

    with pytest.raises(RuntimeError, match="update is in progress"):
        supervisor.acquire(client="agent", session_id="one")

    assert supervisor.processes.running() == {}


def test_runtime_reuses_live_process_after_last_lease_is_released(
    tmp_path: Path,
) -> None:
    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        commands={"local": ("/bin/sleep", "60")},
        idle_shutdown_seconds=60,
    )
    first = supervisor.acquire(client="agent", session_id="one")
    try:
        supervisor.release(str(first["lease_id"]))
        second = supervisor.acquire(client="agent", session_id="two")
        assert second["started"] is False
    finally:
        supervisor.stop(force=True)


def test_runtime_idle_grace_starts_at_the_current_release(
    tmp_path: Path,
) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    supervisor = RuntimeSupervisor(
        paths,
        commands={"local": ("/bin/sleep", "60")},
        idle_shutdown_seconds=60,
    )
    first = supervisor.acquire(client="agent", session_id="one")
    try:
        state = json.loads(paths.runtime_state.read_text(encoding="utf-8"))
        state["last_release_at"] = time.time() - 120
        paths.runtime_state.write_text(json.dumps(state), encoding="utf-8")

        result = supervisor.release(str(first["lease_id"]))

        assert result["stopped"] is False
        assert supervisor.status()["running"] is True
    finally:
        supervisor.stop(force=True)


def test_runtime_idle_watcher_stops_after_grace(tmp_path: Path) -> None:
    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        commands={"local": ("/bin/sleep", "60")},
        idle_shutdown_seconds=0.05,
    )
    lease = supervisor.acquire(client="agent", session_id="one")
    supervisor.release(str(lease["lease_id"]))

    result = supervisor.watch_idle(poll_interval_seconds=0.01)

    assert result["stopped"] is True
    assert result["reason"] == "idle_timeout"
    assert supervisor.status()["running"] is False


def test_runtime_idle_reaper_preserves_home_override(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    installer = paths.current_link / "bin" / "ledgermind"
    installer.parent.mkdir(parents=True)
    installer.write_text("#!/bin/sh\n", encoding="utf-8")
    installer.chmod(0o700)
    supervisor = RuntimeSupervisor(paths, commands={"local": ("/bin/sleep", "60")})

    assert supervisor._idle_reaper_command() == (
        str(installer),
        "runtime",
        "_idle-reap",
        "--home",
        str(tmp_path),
    )


def test_runtime_idle_watcher_reaps_crashed_agent_lease(tmp_path: Path) -> None:
    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        commands={"local": ("/bin/sleep", "60")},
        idle_shutdown_seconds=0.05,
        lease_ttl_seconds=0.05,
    )
    supervisor.acquire(client="agent", session_id="crashed")

    result = supervisor.watch_idle(poll_interval_seconds=0.01)

    assert result["stopped"] is True
    assert result["reason"] == "idle_timeout"
    status = supervisor.status()
    assert status["running"] is False
    assert status["active_leases"] == []


def test_runtime_idle_watcher_cancels_and_rearms_for_new_lease(
    tmp_path: Path,
) -> None:
    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        commands={"local": ("/bin/sleep", "60")},
        idle_shutdown_seconds=0.12,
    )
    first = supervisor.acquire(client="agent", session_id="one")
    supervisor.release(str(first["lease_id"]))
    outcome: dict[str, object] = {}

    def watch() -> None:
        outcome.update(supervisor.watch_idle(poll_interval_seconds=0.01))

    watcher = threading.Thread(target=watch)
    watcher.start()
    time.sleep(0.04)
    second = supervisor.acquire(client="agent", session_id="two")
    time.sleep(0.1)
    assert supervisor.status()["running"] is True
    supervisor.release(str(second["lease_id"]))
    watcher.join(timeout=1)

    assert not watcher.is_alive()
    assert outcome["stopped"] is True
    assert outcome["reason"] == "idle_timeout"


def test_runtime_idle_watcher_waits_for_durable_work_then_full_grace(
    tmp_path: Path,
) -> None:
    work_pending = threading.Event()
    work_pending.set()

    def activity() -> dict[str, object]:
        return {
            "known": True,
            "leased_tasks": 0,
            "pending_writes": 1 if work_pending.is_set() else 0,
        }

    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        commands={"local": ("/bin/sleep", "60")},
        idle_shutdown_seconds=0.12,
        activity_probe=activity,
    )
    lease = supervisor.acquire(client="agent", session_id="long-response")
    supervisor.release(str(lease["lease_id"]))
    outcome: dict[str, object] = {}

    def watch() -> None:
        outcome.update(supervisor.watch_idle(poll_interval_seconds=0.01))

    watcher = threading.Thread(target=watch)
    watcher.start()
    time.sleep(0.18)
    assert supervisor.status()["running"] is True

    work_pending.clear()
    time.sleep(0.06)
    assert supervisor.status()["running"] is True
    watcher.join(timeout=1)

    assert not watcher.is_alive()
    assert outcome["stopped"] is True
    assert outcome["reason"] == "idle_timeout"


def test_runtime_idle_watcher_fails_closed_when_activity_is_unknown(
    tmp_path: Path,
) -> None:
    activity_known = threading.Event()

    def activity() -> dict[str, object]:
        return {
            "known": activity_known.is_set(),
            "leased_tasks": 0,
            "pending_writes": 0,
            "error_code": None if activity_known.is_set() else "core_unavailable",
        }

    supervisor = RuntimeSupervisor(
        InstallerPaths(home_override=tmp_path),
        commands={"local": ("/bin/sleep", "60")},
        idle_shutdown_seconds=0.08,
        activity_probe=activity,
    )
    lease = supervisor.acquire(client="agent", session_id="provider-retry")
    supervisor.release(str(lease["lease_id"]))
    outcome: dict[str, object] = {}

    def watch() -> None:
        outcome.update(supervisor.watch_idle(poll_interval_seconds=0.01))

    watcher = threading.Thread(target=watch)
    watcher.start()
    time.sleep(0.12)
    status = supervisor.status()
    assert status["running"] is True
    assert status["activity"]["known"] is False

    activity_known.set()
    watcher.join(timeout=1)

    assert not watcher.is_alive()
    assert outcome["stopped"] is True
    assert outcome["reason"] == "idle_timeout"


def test_runtime_status_rejects_stale_running_state(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    paths.ensure()
    paths.runtime_state.write_text(
        json.dumps(
            {
                "running": True,
                "endpoint": "http://127.0.0.1:8765",
                "processes": {"local": {"pid": 999_999_999}},
            }
        ),
        encoding="utf-8",
    )
    supervisor = RuntimeSupervisor(
        paths,
        commands={"local": ("/bin/sleep", "60")},
    )

    assert supervisor.status()["running"] is False


def test_runtime_status_requires_every_configured_process(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    paths.ensure()
    paths.runtime_state.write_text(
        json.dumps(
            {
                "running": True,
                "endpoint": "http://127.0.0.1:8765",
                "processes": {
                    "embedding": {"pid": os.getpid(), "command": ["embedding"]}
                },
            }
        ),
        encoding="utf-8",
    )
    supervisor = RuntimeSupervisor(
        paths,
        commands={"local": ("/bin/sleep", "60")},
    )

    assert supervisor.status()["running"] is False


def test_installer_runtime_places_global_home_before_local_subcommand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    paths = InstallerPaths(home_override=tmp_path)
    paths.ensure()
    write_installer_config(_config(), paths)
    release = paths.release_dir("test")
    local = release / "bin" / "ledgermind-local"
    local.parent.mkdir(parents=True)
    local.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    local.chmod(0o700)
    paths.current_link.symlink_to(release)

    supervisor = _runtime(paths)

    assert tuple(supervisor.commands["local"]) == (
        str(paths.current_link / "bin" / "ledgermind-local"),
        "--home",
        str(paths.data_dir / "local"),
        "serve",
    )


def test_runtime_default_command_uses_installed_local_home(
    tmp_path: Path,
) -> None:
    paths = InstallerPaths(home_override=tmp_path)
    paths.ensure()
    release = paths.release_dir("test")
    local = release / "bin" / "ledgermind-local"
    local.parent.mkdir(parents=True)
    local.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    local.chmod(0o700)
    paths.current_link.symlink_to(release)

    supervisor = RuntimeSupervisor(paths)

    assert tuple(supervisor.commands["local"]) == (
        str(paths.current_link / "bin" / "ledgermind-local"),
        "--home",
        str(paths.data_dir / "local"),
        "serve",
    )


def test_local_embedding_service_is_openai_compatible() -> None:
    service = EmbeddingService(
        backend=lambda texts: [[float(len(text)), 1.0, 0.0] for text in texts],
        model="local-model",
        dimensions=3,
        device="cpu",
    )
    endpoint = service.start()
    try:
        request = Request(
            endpoint + "/embeddings",
            data=json.dumps({"model": "local-model", "input": ["hello"]}).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode())
        assert payload["data"][0]["embedding"] == [5.0, 1.0, 0.0]
    finally:
        service.stop()


def test_local_embedding_service_forwards_query_passage_role() -> None:
    roles: list[str | None] = []

    def backend(texts: list[str], *, role: str | None = None) -> list[list[float]]:
        roles.append(role)
        return [[1.0, 0.0, 0.0] for _ in texts]

    service = EmbeddingService(
        backend=backend,
        model="local-model",
        dimensions=3,
        device="cpu",
    )
    endpoint = service.start()
    try:
        request = Request(
            endpoint + "/embeddings",
            data=json.dumps(
                {"model": "local-model", "input": ["hello"], "input_type": "query"}
            ).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            assert response.status == 200
        assert roles == ["query"]
    finally:
        service.stop()


def test_api_embedding_profile_does_not_spawn_local_embedding_service() -> None:
    config = LocalConfig(
        config_version=2,
        semantic_language="en",
        embedding=LocalEmbeddingConfig(
            enabled=True,
            provider_mode="api",
            endpoint="https://provider.example/v1",
            model="embedding-model",
            dimensions=3,
        ),
    )

    supervisor = _build_runtime_supervisor(config=config, host="127.0.0.1", port=8765)

    assert "embedding" not in supervisor.commands
    assert supervisor.automatic_shutdown is False
    assert supervisor.process_owner is False


def test_local_embedding_profile_does_not_give_bridge_process_ownership() -> None:
    config = LocalConfig(
        config_version=2,
        semantic_language="en",
        embedding=LocalEmbeddingConfig(
            enabled=True,
            provider_mode="local",
            model="embedding-model",
            model_path="/tmp/embedding-model",
            dimensions=3,
        ),
    )

    supervisor = _build_runtime_supervisor(config=config, host="127.0.0.1", port=8765)

    assert supervisor.commands == {}
    assert supervisor.process_owner is False


def test_installed_local_embedding_uses_its_signed_device_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    paths = InstallerPaths(home_override=tmp_path)
    paths.ensure()
    release = paths.release_dir("test")
    (release / "bin").mkdir(parents=True)
    local = release / "bin" / "ledgermind-local"
    local.write_text("#!/bin/sh\n", encoding="utf-8")
    local.chmod(0o700)
    paths.current_link.symlink_to(release)
    runtime = paths.data_dir / "embedding-runtimes" / "nemotron" / "cpu"
    runtime_python = runtime / "bin" / "python3"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime_python.chmod(0o700)
    config = _config().model_copy(
        update={
            "embedding": EmbeddingConfig(
                mode="local",
                local=InstallerLocalEmbeddingConfig(
                    catalog_id="nemotron",
                    device="cpu",
                    model_storage_path=str(paths.models_dir / "nemotron"),
                    runtime_id="nemotron",
                    runtime_path=str(runtime),
                    dimensions=2048,
                ),
            )
        }
    )
    write_installer_config(config, paths)

    command = tuple(_runtime(paths).commands["embedding"])

    assert command[0] == str(runtime_python)
    assert "sentence_transformers" not in " ".join(command)
    assert command[command.index("--model") + 1] == "nemotron"
    assert command[command.index("--dimensions") + 1] == "2048"
    assert "--token-file" in command
    assert (
        paths.data_dir / "embedding" / "server.token"
    ).stat().st_mode & 0o777 == 0o600
    assert "embedding-local" not in " ".join(command)
