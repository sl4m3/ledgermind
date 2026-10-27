"""Wheel content checks for the clean local package."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

_FORBIDDEN_TOP_LEVEL = {
    "application",
    "contracts",
    "domain",
    "ports",
    "api",
    "persistence",
}
_FORBIDDEN_COMPONENTS = {
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
_FORBIDDEN_SECRET_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".token"}
_FORBIDDEN_DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
_REQUIRED_RUNTIME_FILES = {
    "ledgermind_local.persistence/rounds_migrations/0001_initial.sql",
    "ledgermind_local.persistence/rounds_migrations/0002_projection_state_compat.sql",
    "ledgermind_local.persistence/rounds_migrations/0003_core_projection_inbox.sql",
    "ledgermind_local.persistence/rounds_migrations/0004_core_projection_fts.sql",
    "ledgermind_local.persistence/rounds_migrations/0005_worker_leases.sql",
    "ledgermind_local.persistence/rounds_migrations/0006_object_facet_core_delivery.sql",
    "ledgermind_local.persistence/rounds_migrations/0007_contract_naming.sql",
    "ledgermind_local.persistence/rounds_migrations/0008_provider_capabilities.sql",
    "ledgermind_local.persistence/rounds_migrations/0009_provider_capability_cache.sql",
    "ledgermind_local.persistence/rounds_migrations/0010_embedding_vector_cache.sql",
    "ledgermind_local.persistence/rounds_migrations/0011_generation_provider_options.sql",
    "ledgermind_local.persistence/rounds_migrations/0012_strict_provider_capability_mode.sql",
    "ledgermind_local.persistence/rounds_migrations/0013_object_resolution_profile_slot.sql",
    "ledgermind_local.persistence/rounds_migrations/0014_provider_kind_nvidia.sql",
    "ledgermind_local.persistence/contract_migration.py",
    "ledgermind_local.core_gateway/contracts.py",
    "ledgermind_local.core_gateway/compatibility.py",
    "ledgermind_local.core_gateway/process.py",
    "ledgermind_local.inference/vectorizer.py",
    "ledgermind_local.scheduler/core_execution_task_worker.py",
}


def _build_wheel_names(source: Path, tmp_path: Path) -> list[str]:
    checkout = tmp_path / "checkout"
    shutil.copytree(
        source,
        checkout,
        ignore=shutil.ignore_patterns(
            ".git",
            ".pytest_cache",
            ".venv",
            "__pycache__",
            "build",
            "dist",
            "*.egg-info",
        ),
    )
    wheel_dir = tmp_path / "wheels"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(wheel_dir),
            ".",
        ],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheel_dir.glob("*.whl"))
    with ZipFile(wheel) as archive:
        return archive.namelist()


def _build_sdist_names(source: Path, tmp_path: Path) -> list[str]:
    checkout = tmp_path / "sdist-checkout"
    shutil.copytree(
        source,
        checkout,
        ignore=shutil.ignore_patterns(
            ".git",
            ".pytest_cache",
            ".venv",
            "__pycache__",
            "build",
            "dist",
            "*.egg-info",
        ),
    )
    sdist_dir = tmp_path / "sdists"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--sdist",
            "--no-isolation",
            "--outdir",
            str(sdist_dir),
            ".",
        ],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    )
    sdist = next(sdist_dir.glob("*.tar.gz"))
    with tarfile.open(sdist, "r:gz") as archive:
        return [member.name for member in archive.getmembers()]


def test_clean_local_wheel_contains_only_namespaced_package(tmp_path: Path) -> None:
    names = _build_wheel_names(Path(__file__).resolve().parents[2], tmp_path)
    top_level = {name.split("/", 1)[0] for name in names if "/" in name}
    assert "ledgermind_local" in top_level
    assert not top_level & _FORBIDDEN_TOP_LEVEL


def test_local_wheel_contains_runtime_data_and_no_release_artifacts(
    tmp_path: Path,
) -> None:
    names = _build_wheel_names(Path(__file__).resolve().parents[2], tmp_path)
    normalized = {name.replace("/", ".", 1) if name.startswith("ledgermind_local/") else name for name in names}
    paths = {Path(name) for name in names}

    assert _REQUIRED_RUNTIME_FILES <= normalized
    assert not any(
        component in _FORBIDDEN_COMPONENTS
        for path in paths
        for component in path.parts
    )
    assert not any(path.suffix.lower() == ".pyc" for path in paths)
    assert not any(path.parts[0] == "tests" for path in paths)
    assert not any(
        path.suffix.lower() in _FORBIDDEN_DATABASE_SUFFIXES
        for path in paths
    )
    forbidden_secret_names = {
        ".env",
        ".env.example",
        "credentials",
        "credentials.json",
        "private_key",
        "private_key.json",
        "secret",
        "secret.json",
    }
    assert not any(
        path.name.lower() in forbidden_secret_names
        or path.suffix.lower() in _FORBIDDEN_SECRET_SUFFIXES
        for path in paths
    )
    assert not any(re.search(r"(^|/)build-copy(/|$)", name) for name in names)


def test_clean_local_sdist_contains_source_without_generated_artifacts(
    tmp_path: Path,
) -> None:
    names = _build_sdist_names(Path(__file__).resolve().parents[2], tmp_path)
    paths = {Path(name) for name in names}

    assert any(path.name == "pyproject.toml" for path in paths)
    assert any(
        path.parts[-3:] == ("src", "ledgermind_local", "__init__.py")
        for path in paths
    )
    assert not any(
        component in _FORBIDDEN_COMPONENTS or component == ".git"
        for path in paths
        for component in path.parts
    )
    assert not any(path.suffix.lower() in {".pyc", ".pyo"} for path in paths)
    assert not any(
        path.suffix.lower() in _FORBIDDEN_DATABASE_SUFFIXES
        for path in paths
    )
    assert not any(
        path.name.lower() in {
            ".env",
            ".env.example",
            "credentials",
            "credentials.json",
            "private_key",
            "private_key.json",
            "secret",
            "secret.json",
        }
        or path.suffix.lower() in _FORBIDDEN_SECRET_SUFFIXES
        for path in paths
    )
