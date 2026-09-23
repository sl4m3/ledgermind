from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ledgermind_local.core_gateway.isolation import IsolationRequirements
from ledgermind_local.core_gateway.sandbox import (
    SandboxLevel,
    SandboxUnavailableError,
    _ProbeResult,
    _sandbox_environment,
    _sanitized_environment,
    build_sandbox_plan,
)


def test_missing_network_sandbox_is_partial_when_not_required(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox.shutil.which",
        lambda _: None,
    )

    plan = build_sandbox_plan(
        ("/opt/ledgermind-core/bin/ledgermind-core", "--database", "knowledge.db"),
        core_data_dir=tmp_path,
        required=False,
    )

    assert plan.level is SandboxLevel.PARTIAL
    assert plan.command == (
        "/opt/ledgermind-core/bin/ledgermind-core",
        "--database",
        "knowledge.db",
    )


def test_missing_required_network_sandbox_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox.shutil.which",
        lambda _: None,
    )

    with pytest.raises(SandboxUnavailableError):
        build_sandbox_plan(
            ("/opt/ledgermind-core/bin/ledgermind-core",),
            core_data_dir=tmp_path,
            required=True,
        )


def test_bwrap_plan_is_full_only_after_probe(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox._probe_command",
        lambda command, core_data_dir: (
            _ProbeResult(
                network_isolated=True,
                rounds_database_hidden=True,
                filesystem_allowlisted=True,
                environment_sanitized=True,
                file_descriptors_closed=True,
            )
            if command[0] == "/usr/bin/bwrap"
            else None
        ),
    )

    plan = build_sandbox_plan(
        ("/opt/ledgermind-core/bin/ledgermind-core", "--database", "knowledge.db"),
        core_data_dir=tmp_path,
        required=True,
    )

    assert plan.level is SandboxLevel.FULL
    assert plan.command[:3] == (
        "/usr/bin/bwrap",
        "--unshare-user",
        "--unshare-net",
    )
    assert plan.command[-4:] == (
        "--",
        "/opt/ledgermind-core/bin/ledgermind-core",
        "--database",
        "knowledge.db",
    )


def test_bwrap_plan_masks_blocked_local_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox._probe_command",
        lambda command, core_data_dir: _ProbeResult(
            network_isolated=True,
            rounds_database_hidden=True,
            filesystem_allowlisted=True,
            environment_sanitized=True,
            file_descriptors_closed=True,
        ),
    )
    local_data_dir = tmp_path / "local"

    plan = build_sandbox_plan(
        ("/opt/ledgermind-core/bin/ledgermind-core",),
        core_data_dir=tmp_path / "core",
        blocked_data_dirs=(local_data_dir,),
        required=True,
    )

    assert plan.level is SandboxLevel.FULL
    tmpfs_args = plan.command[plan.command.index("--tmpfs") :]
    assert str(local_data_dir) in tmpfs_args


def test_explicit_runtime_paths_are_added_to_the_read_only_allowlist(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox._probe_command",
        lambda command, core_data_dir: _ProbeResult(
            network_isolated=True,
            rounds_database_hidden=True,
            filesystem_allowlisted=True,
            environment_sanitized=True,
            file_descriptors_closed=True,
        ),
    )
    runtime_path = tmp_path / "runtime" / "src"
    runtime_path.mkdir(parents=True)

    plan = build_sandbox_plan(
        ("/opt/ledgermind-core/bin/ledgermind-core",),
        core_data_dir=tmp_path / "core",
        runtime_paths=(runtime_path,),
        required=True,
    )

    ro_bind_index = plan.command.index("--ro-bind")
    assert plan.command[ro_bind_index + 1 : ro_bind_index + 3] == (
        str(runtime_path),
        str(runtime_path),
    )


def test_core_database_argument_remains_writable_inside_core_data_dir(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox._probe_command",
        lambda command, core_data_dir: _ProbeResult(
            network_isolated=True,
            rounds_database_hidden=True,
            filesystem_allowlisted=True,
            environment_sanitized=True,
            file_descriptors_closed=True,
        ),
    )
    core_data_dir = tmp_path / "core"
    core_data_dir.mkdir()
    database = core_data_dir / "knowledge.db"
    database.write_bytes(b"core-owned database")

    plan = build_sandbox_plan(
        ("/opt/ledgermind-core/bin/ledgermind-core", "--database", str(database)),
        core_data_dir=core_data_dir,
        required=True,
    )

    read_only_destinations = {
        plan.command[index + 2]
        for index, value in enumerate(plan.command)
        if value == "--ro-bind"
    }
    assert str(database) not in read_only_destinations


def test_unshare_probe_reports_network_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox.shutil.which",
        lambda name: "/usr/bin/unshare" if name == "unshare" else None,
    )
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox._probe_command",
        lambda command, core_data_dir: _ProbeResult(
            network_isolated=True,
            rounds_database_hidden=False,
            filesystem_allowlisted=False,
            environment_sanitized=True,
            file_descriptors_closed=True,
        ),
    )

    plan = build_sandbox_plan(
        ("/opt/ledgermind-core/bin/ledgermind-core",),
        core_data_dir=tmp_path,
        requirements=IsolationRequirements(
            require_network_isolation=True,
            require_filesystem_allowlist=True,
        ),
        required=False,
    )

    assert plan.capabilities.network_isolated is True
    assert plan.capabilities.filesystem_allowlisted is False
    assert plan.level is SandboxLevel.PARTIAL
    assert plan.capabilities.sandbox_backend == "unshare"


def test_permissive_profile_reports_missing_capabilities(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox.shutil.which",
        lambda _: None,
    )
    blocked_data_dir = tmp_path / "local"
    blocked_data_dir.mkdir()
    rounds_database = blocked_data_dir / "rounds.db"
    rounds_database.write_bytes(b"local-owned fixture")

    plan = build_sandbox_plan(
        ("/opt/ledgermind-core/bin/ledgermind-core",),
        core_data_dir=tmp_path / "core",
        blocked_data_dirs=(blocked_data_dir,),
        rounds_database_path=rounds_database,
        requirements=IsolationRequirements(
            require_network_isolation=True,
            require_rounds_database_hidden=True,
            require_filesystem_allowlist=True,
        ),
        required=False,
    )

    assert plan.command == ("/opt/ledgermind-core/bin/ledgermind-core",)
    assert plan.capabilities.network_isolated is False
    assert plan.capabilities.rounds_database_hidden is False
    assert plan.capabilities.filesystem_allowlisted is False
    assert plan.capabilities.sandbox_backend == "none"


def test_sanitized_environment_allows_locale_context_but_not_secrets(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LC_CTYPE", "C.UTF-8")
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("OPENAI_API_KEY", "[REDACTED]")
    monkeypatch.setenv("PYTHONHOME", "/unexpected")

    environment = _sanitized_environment(tmp_path)

    assert environment["LC_CTYPE"] == "C.UTF-8"
    assert environment["TZ"] == "UTC"
    assert "OPENAI_API_KEY" not in environment
    assert "PYTHONHOME" not in environment


def test_pythonhome_is_only_injected_for_a_python_shim(tmp_path: Path) -> None:
    rust_environment = _sandbox_environment(
        tmp_path,
        ("/opt/ledgermind-core/bin/ledgermind-core",),
    )
    shim_environment = _sandbox_environment(tmp_path, (sys.executable,))

    assert "PYTHONHOME" not in rust_environment
    assert shim_environment["PYTHONHOME"] == sys.base_prefix


def test_sandbox_environment_preserves_semantic_language_contract(
    tmp_path: Path,
) -> None:
    environment = _sandbox_environment(
        tmp_path,
        ("/opt/ledgermind-core/bin/ledgermind-core",),
        semantic_language="ru",
    )

    assert environment["LEDGERMIND_SEMANTIC_LANGUAGE"] == "ru"
