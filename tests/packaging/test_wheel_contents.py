"""Wheel content checks for the clean core package."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

_FORBIDDEN_TOP_LEVEL = {"application", "contracts", "domain", "ports", "api", "persistence"}


def _build_wheel_names(source: Path, tmp_path: Path) -> list[str]:
    checkout = tmp_path / "checkout"
    shutil.copytree(
        source,
        checkout,
        ignore=shutil.ignore_patterns(
            ".git",
            ".pytest_cache",
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


def test_clean_core_wheel_contains_only_namespaced_package(tmp_path: Path) -> None:
    names = _build_wheel_names(Path(__file__).resolve().parents[2], tmp_path)
    top_level = {name.split("/", 1)[0] for name in names if "/" in name}
    assert "ledgermind_core" in top_level
    assert not top_level & _FORBIDDEN_TOP_LEVEL
