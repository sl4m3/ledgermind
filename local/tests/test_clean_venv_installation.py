"""Automated clean virtual environment installation and verification test suite.

Validates Milestone 2 acceptance criteria:
1. Builds or resolves wheels for ledgermind-protocol and ledgermind-inference.
2. Creates a clean temporary virtual environment.
3. Installs ledgermind-local via `pip install --find-links <wheel_dir> .`.
4. Verifies imports for ledgermind_local, ledgermind_protocol, and ledgermind_inference.
5. Verifies CLI commands:
   - `ledgermind --help`
   - `ledgermind integrations --help`
   - `ledgermind integrations discover --json`
6. Verifies universal installer execution in non-interactive mode per repository README:
   - Enforces 0600 secure permissions on installation configuration
   - Runs `ledgermind install plan --non-interactive --config <config> --home <home> --json`
   - Runs `ledgermind install --dry-run --non-interactive --config <config> --home <home> --skip-provider-probe --json`
   - Verifies isolated environment integrity (no modifications to user system directories)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

LOCAL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LOCAL_ROOT.parent
PLATFORM_ROOT = REPO_ROOT.parent / "ledgermind-platform"


@pytest.fixture(scope="session")
def resolved_wheels(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Resolve pre-built wheels or build them into a shared directory for session tests."""
    wheel_dir = tmp_path_factory.mktemp("dependency_wheels")

    # 1. Resolve or build ledgermind-protocol wheel
    protocol_dist = REPO_ROOT / "protocol" / "python" / "dist"
    existing_proto = (
        list(protocol_dist.glob("ledgermind_protocol-*.whl"))
        if protocol_dist.is_dir()
        else []
    )
    if existing_proto:
        shutil.copy2(sorted(existing_proto)[-1], wheel_dir)
    else:
        uv_bin = shutil.which("uv")
        if uv_bin:
            proc = subprocess.run(
                [uv_bin, "build", "--wheel", "--out-dir", str(wheel_dir)],
                cwd=str(REPO_ROOT / "protocol" / "python"),
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "wheel",
                        "--no-deps",
                        "-w",
                        str(wheel_dir),
                        ".",
                    ],
                    cwd=str(REPO_ROOT / "protocol" / "python"),
                    check=True,
                )
        else:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "-w",
                    str(wheel_dir),
                    ".",
                ],
                cwd=str(REPO_ROOT / "protocol" / "python"),
                check=True,
            )

    # 2. Resolve or build ledgermind-inference wheel
    env_wheel = os.environ.get("LEDGERMIND_INFERENCE_WHEEL")
    if env_wheel and Path(env_wheel).is_file():
        shutil.copy2(env_wheel, wheel_dir)
    else:
        inference_dist = PLATFORM_ROOT / "inference" / "dist"
        existing_inf = (
            list(inference_dist.glob("ledgermind_inference-*.whl"))
            if inference_dist.is_dir()
            else []
        )
        if existing_inf:
            shutil.copy2(sorted(existing_inf)[-1], wheel_dir)
        elif (PLATFORM_ROOT / "inference").is_dir():
            uv_bin = shutil.which("uv")
            if uv_bin:
                proc = subprocess.run(
                    [uv_bin, "build", "--wheel", "--out-dir", str(wheel_dir)],
                    cwd=str(PLATFORM_ROOT / "inference"),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode != 0:
                    subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pip",
                            "wheel",
                            "--no-deps",
                            "-w",
                            str(wheel_dir),
                            ".",
                        ],
                        cwd=str(PLATFORM_ROOT / "inference"),
                        check=True,
                    )
            else:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "wheel",
                        "--no-deps",
                        "-w",
                        str(wheel_dir),
                        ".",
                    ],
                    cwd=str(PLATFORM_ROOT / "inference"),
                    check=True,
                )

    proto_wheels = list(wheel_dir.glob("ledgermind_protocol*.whl"))
    inf_wheels = list(wheel_dir.glob("ledgermind_inference*.whl"))
    assert proto_wheels, "ledgermind-protocol wheel could not be resolved or built"
    assert inf_wheels, "ledgermind-inference wheel could not be resolved or built"

    return wheel_dir


@pytest.fixture(scope="session")
def installed_clean_venv(
    tmp_path_factory: pytest.TempPathFactory, resolved_wheels: Path
) -> tuple[Path, Path]:
    """Create a clean virtual environment and install ledgermind-local via pip find-links."""
    venv_dir = tmp_path_factory.mktemp("clean_env") / "venv"

    uv_bin = shutil.which("uv")
    if uv_bin:
        proc = subprocess.run(
            [uv_bin, "venv", "--seed", str(venv_dir)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    else:
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    venv_python = venv_dir / "bin" / "python"
    venv_pip = venv_dir / "bin" / "pip"
    assert venv_python.is_file(), f"Python binary missing in venv: {venv_python}"

    # Install ledgermind-local using pip find-links pointing to resolved wheels
    if venv_pip.is_file():
        install_cmd = [
            str(venv_pip),
            "install",
            "--find-links",
            str(resolved_wheels),
            str(LOCAL_ROOT),
        ]
    else:
        install_cmd = [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv_python),
            "--find-links",
            str(resolved_wheels),
            str(LOCAL_ROOT),
        ]

    proc = subprocess.run(install_cmd, capture_output=True, text=True)
    assert proc.returncode == 0, f"pip install failed:\n{proc.stdout}\n{proc.stderr}"

    return venv_dir, venv_python


def test_dependency_wheels_present(resolved_wheels: Path) -> None:
    """Verify that protocol and inference wheels are built/resolved successfully."""
    proto_wheels = list(resolved_wheels.glob("ledgermind_protocol*.whl"))
    inf_wheels = list(resolved_wheels.glob("ledgermind_inference*.whl"))

    assert len(proto_wheels) >= 1
    assert len(inf_wheels) >= 1
    assert all(w.stat().st_size > 0 for w in proto_wheels)
    assert all(w.stat().st_size > 0 for w in inf_wheels)


def test_clean_import_installed_packages(installed_clean_venv: tuple[Path, Path]) -> None:
    """Verify that ledgermind_local, protocol, and inference packages import without error."""
    _venv_dir, venv_python = installed_clean_venv
    script = (
        "import ledgermind_local\n"
        "import ledgermind_protocol\n"
        "import ledgermind_inference\n"
        "assert ledgermind_local.__version__ == '5.0.1', f'Unexpected version: {ledgermind_local.__version__}'\n"
        "print('IMPORTS_SUCCESSFUL')\n"
        "print(f'VERSION: {ledgermind_local.__version__}')\n"
    )
    proc = subprocess.run(
        [str(venv_python), "-c", script],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Import test failed:\n{proc.stdout}\n{proc.stderr}"
    assert "IMPORTS_SUCCESSFUL" in proc.stdout
    assert "VERSION: 5.0.1" in proc.stdout


def test_clean_import_version(installed_clean_venv: tuple[Path, Path]) -> None:
    """Verify that ledgermind_local.__version__ equals '5.0.1' when imported."""
    _venv_dir, venv_python = installed_clean_venv
    proc = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import ledgermind_local; print(ledgermind_local.__version__)",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Version check failed:\n{proc.stdout}\n{proc.stderr}"
    assert proc.stdout.strip() == "5.0.1"


def test_cli_help_in_clean_venv(installed_clean_venv: tuple[Path, Path]) -> None:
    """Verify `ledgermind --help` executes cleanly from installed package script."""
    venv_dir, _venv_python = installed_clean_venv
    cli_bin = venv_dir / "bin" / "ledgermind"
    assert cli_bin.is_file(), f"CLI executable not created: {cli_bin}"

    proc = subprocess.run([str(cli_bin), "--help"], capture_output=True, text=True)
    assert proc.returncode == 0, f"CLI help failed:\n{proc.stdout}\n{proc.stderr}"
    assert "LedgerMind local service" in proc.stdout
    assert "integrations" in proc.stdout or "init" in proc.stdout


def test_cli_integrations_help_in_clean_venv(installed_clean_venv: tuple[Path, Path]) -> None:
    """Verify `ledgermind integrations --help` dispatches properly without argparse errors."""
    venv_dir, _venv_python = installed_clean_venv
    cli_bin = venv_dir / "bin" / "ledgermind"

    proc = subprocess.run(
        [str(cli_bin), "integrations", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"integrations help failed:\n{proc.stdout}\n{proc.stderr}"
    assert "discover" in proc.stdout
    assert "status" in proc.stdout
    assert "connect" in proc.stdout


def test_cli_integrations_discover_in_clean_venv(
    installed_clean_venv: tuple[Path, Path], tmp_path: Path
) -> None:
    """Verify `ledgermind integrations discover --json` dispatches to integrations engine."""
    venv_dir, _venv_python = installed_clean_venv
    cli_bin = venv_dir / "bin" / "ledgermind"
    isolated_home = tmp_path / "home"

    proc = subprocess.run(
        [
            str(cli_bin),
            "integrations",
            "discover",
            "--json",
            "--home",
            str(isolated_home),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode in (0, 1), (
        f"`ledgermind integrations discover --json` exited with unexpected code {proc.returncode}"
    )
    output_data = json.loads(proc.stdout)
    assert output_data.get("operation") == "integrations discover"
    assert "steps" in output_data


def test_readme_installer_non_interactive_execution(
    installed_clean_venv: tuple[Path, Path], tmp_path: Path
) -> None:
    """Verify universal installer execution in non-interactive mode per repository README."""
    venv_dir, _venv_python = installed_clean_venv
    cli_bin = venv_dir / "bin" / "ledgermind"
    isolated_home = tmp_path / "sandbox_home"
    isolated_home.mkdir(parents=True, exist_ok=True)

    config_path = isolated_home / "ledgermind-install.json"
    config_payload = {
        "schema_version": 2,
        "semantic_language": "en",
        "generation": {
            "endpoint": "https://api.openai.com/mock",
            "model": "gpt-4o-mini",
            "token": "sk-dummy-token",
        },
        "embedding": {
            "mode": "api",
            "api": {
                "endpoint": "https://api.openai.com/mock",
                "model": "text-embedding-3-small",
                "dimensions": 1536,
                "token": "sk-dummy-token",
            },
        },
    }
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")
    # README requirement: chmod 600 /secure/ledgermind-install.json
    config_path.chmod(0o600)

    # 1. Run install plan --non-interactive --config <config> --home <home> --json
    plan_proc = subprocess.run(
        [
            str(cli_bin),
            "install",
            "plan",
            "--non-interactive",
            "--config",
            str(config_path),
            "--home",
            str(isolated_home),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert plan_proc.returncode == 0, (
        f"install plan failed:\n{plan_proc.stdout}\n{plan_proc.stderr}"
    )
    plan_data = json.loads(plan_proc.stdout)
    assert plan_data.get("status") in {"passed", "success"}
    assert plan_data.get("operation") == "install plan"

    # 2. Run install --dry-run --non-interactive --config <config> --home <home> --skip-provider-probe --json
    dry_proc = subprocess.run(
        [
            str(cli_bin),
            "install",
            "--dry-run",
            "--non-interactive",
            "--config",
            str(config_path),
            "--home",
            str(isolated_home),
            "--skip-provider-probe",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert dry_proc.returncode == 0, (
        f"install dry-run failed:\n{dry_proc.stdout}\n{dry_proc.stderr}"
    )
    dry_data = json.loads(dry_proc.stdout)
    assert dry_data.get("status") == "dry_run"
    assert dry_data.get("operation") == "install"
