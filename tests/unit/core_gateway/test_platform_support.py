from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

import pytest

from ledgermind_local.core_gateway.isolation import IsolationRequirements
from ledgermind_local.core_gateway.sandbox import (
    SandboxLevel,
    SandboxUnavailableError,
    build_sandbox_plan,
)

_SUPPORTED_LINUX_ARCHITECTURES = frozenset({"x86_64", "aarch64"})
_SECURE_REQUIREMENTS = IsolationRequirements(
    require_network_isolation=True,
    require_rounds_database_hidden=True,
    require_filesystem_allowlist=True,
    require_environment_sanitized=True,
)


def test_secure_release_platform_is_linux_x86_64_or_aarch64() -> None:
    if sys.platform != "linux":
        pytest.skip("secure release policy targets Linux only")

    assert platform.machine().lower() in _SUPPORTED_LINUX_ARCHITECTURES


def test_real_bwrap_secure_probe_or_explicit_unavailable_skip(tmp_path: Path) -> None:
    if sys.platform != "linux":
        pytest.skip("bwrap secure-release probe targets Linux only")
    if platform.machine().lower() not in _SUPPORTED_LINUX_ARCHITECTURES:
        pytest.skip("host architecture is outside the secure-release targets")

    bwrap = shutil.which("bwrap")
    if bwrap is None:
        pytest.skip("bwrap is unavailable; secure production launch must fail closed")

    core_data_dir = tmp_path / "core"
    core_data_dir.mkdir(mode=0o700)
    local_data_dir = tmp_path / "local"
    local_data_dir.mkdir(mode=0o700)
    rounds_database = local_data_dir / "rounds.db"
    rounds_database.write_bytes(b"local-owned fixture")

    try:
        plan = build_sandbox_plan(
            (sys.executable, "-c", "pass"),
            core_data_dir=core_data_dir,
            blocked_data_dirs=(local_data_dir,),
            rounds_database_path=rounds_database,
            requirements=_SECURE_REQUIREMENTS,
            required=True,
            strict=True,
        )
    except SandboxUnavailableError as exc:
        pytest.fail(
            f"bwrap is installed at {bwrap!r} but the secure capability probe failed: {exc}"
        )

    assert plan.level is SandboxLevel.FULL
    assert plan.capabilities.sandbox_backend == "bwrap"
    assert plan.capabilities.network_isolated is True
    assert plan.capabilities.rounds_database_hidden is True
    assert plan.capabilities.filesystem_allowlisted is True
    assert plan.capabilities.environment_sanitized is True
    assert plan.capabilities.file_descriptors_closed is True


def test_dockerfile_declares_experimental_unsupported_status() -> None:
    dockerfile = Path(__file__).parents[3] / "Dockerfile"
    content = dockerfile.read_text(encoding="utf-8").lower()

    assert 'io.ledgermind.deployment.status="experimental-unsupported"' in content
    assert 'io.ledgermind.secure-deployment="unsupported"' in content
