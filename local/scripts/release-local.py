#!/usr/bin/env python3
"""Build and verify a clean LedgerMind Local Python release.

The checkout is only used as a clean Git source of truth.  Packaging, wheel
inspection, installation, smoke tests, and the release manifest all happen in
external temporary/output directories so a successful release cannot leave a
``dist`` or ``egg-info`` copy that is accidentally published later.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import tomllib

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = "ledgermind-local"
MANIFEST_NAME = f"{COMPONENT}-manifest.json"
PACKAGE = "ledgermind_local"
REQUIRED_IMPORTS = (
    "ledgermind_local.core_gateway.isolation",
    "ledgermind_local.core_gateway.maintenance",
    "ledgermind_local.core_gateway.process",
    "ledgermind_local.persistence.contract_migration",
    "ledgermind_local.inference.vectorizer",
    "ledgermind_local.scheduler.core_execution_task_worker",
    "ledgermind_local.scheduler.guarded_loop",
    "ledgermind_local.scheduler.retention_worker",
)
REQUIRED_WHEEL_FILES = {
    "ledgermind_local/__init__.py",
    "ledgermind_local/core_gateway/isolation.py",
    "ledgermind_local/core_gateway/maintenance.py",
    "ledgermind_local/core_gateway/process.py",
    "ledgermind_local/core_gateway/contracts.py",
    "ledgermind_local/inference/vectorizer.py",
    "ledgermind_local/scheduler/core_execution_task_worker.py",
    "ledgermind_local/scheduler/guarded_loop.py",
    "ledgermind_local/scheduler/retention_worker.py",
    "ledgermind_local/persistence/rounds_migrations/0001_initial.sql",
    "ledgermind_local/persistence/rounds_migrations/0005_worker_leases.sql",
    "ledgermind_local/persistence/rounds_migrations/0006_object_facet_core_delivery.sql",
    "ledgermind_local/persistence/rounds_migrations/0007_contract_naming.sql",
    "ledgermind_local/persistence/contract_migration.py",
    "ledgermind_local/persistence/rounds_migrations/0002_projection_state_compat.sql",
    "ledgermind_local/persistence/rounds_migrations/0003_core_projection_inbox.sql",
    "ledgermind_local/persistence/rounds_migrations/0004_core_projection_fts.sql",
}
_GENERATED_DIR_NAMES = {
    "build",
    "dist",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    ".tox",
    ".nox",
}
_GENERATED_FILE_SUFFIXES = {".pyc", ".pyo"}
_GENERATED_FILE_NAMES = {".coverage"}
_FORBIDDEN_WHEEL_COMPONENTS = _GENERATED_DIR_NAMES | {"tests", "plans", "audits"}
_FORBIDDEN_SECRET_NAMES = {
    ".env",
    ".env.example",
    "credentials",
    "credentials.json",
    "private_key",
    "private_key.json",
    "secret",
    "secret.json",
}
_FORBIDDEN_SECRET_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".token"}
_FORBIDDEN_DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
_LICENSE_FILE_NAMES = {"LICENSE", "NOTICE", "COPYING"}


class ReleaseError(RuntimeError):
    """A release precondition or verification check failed."""


def _run(
    command: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if process.returncode:
        details = (process.stderr or process.stdout).strip()
        if len(details) > 4_000:
            details = details[-4_000:]
        raise ReleaseError(
            f"command failed ({process.returncode}): {' '.join(map(str, command))}\n{details}"
        )
    return process


def _git(root: Path, *arguments: str) -> str:
    return _run(("git", *arguments), cwd=root).stdout.strip()


def _git_state(root: Path) -> tuple[str, int]:
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ReleaseError(
            "release requires a clean Git checkout; changed paths:\n" + status
        )
    commit = _git(root, "rev-parse", "HEAD")
    commit_epoch = int(_git(root, "show", "-s", "--format=%ct", "HEAD"))
    return commit, commit_epoch


def _project_manifest(root: Path) -> dict[str, Any]:
    with (root / "pyproject.toml").open("rb") as handle:
        value = tomllib.load(handle)
    if not isinstance(value, dict):
        raise ReleaseError("pyproject.toml must contain a TOML table")
    return value


def _version(root: Path) -> str:
    value = _project_manifest(root).get("project", {}).get("version")
    if not isinstance(value, str) or not value:
        raise ReleaseError("pyproject.toml does not define project.version")
    return value


def _cleanup_generated(root: Path) -> None:
    """Remove only known build/test artifacts, never arbitrary user files."""

    for current, directories, files in os.walk(root, topdown=True):
        current_path = Path(current)
        if any(part in {".git", ".venv", "venv", "env", "ENV"} for part in current_path.parts):
            directories[:] = []
            continue
        kept: list[str] = []
        for name in directories:
            path = current_path / name
            if name in _GENERATED_DIR_NAMES or name.endswith(".egg-info"):
                shutil.rmtree(path)
            else:
                kept.append(name)
        directories[:] = kept
        for name in files:
            path = current_path / name
            if name in _GENERATED_FILE_NAMES or path.suffix in _GENERATED_FILE_SUFFIXES:
                path.unlink(missing_ok=True)


def _assert_no_generated(root: Path) -> None:
    found: list[str] = []
    for current, directories, files in os.walk(root):
        current_path = Path(current)
        if any(part in {".git", ".venv", "venv", "env", "ENV"} for part in current_path.parts):
            directories[:] = []
            continue
        for name in directories:
            if name in _GENERATED_DIR_NAMES or name.endswith(".egg-info"):
                found.append(str(current_path / name))
        for name in files:
            path = current_path / name
            if name in _GENERATED_FILE_NAMES or path.suffix in _GENERATED_FILE_SUFFIXES:
                found.append(str(path))
    if found:
        raise ReleaseError("generated artifacts remain in checkout:\n" + "\n".join(found))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_checkout(root: Path, destination: Path) -> tuple[Path, str]:
    archive_path = destination / "source.tar"
    _run(
        ("git", "archive", "--format=tar", "--output", archive_path, "HEAD"),
        cwd=root,
    )
    source = destination / "source"
    source.mkdir()
    with tarfile.open(archive_path) as archive:
        archive.extractall(source)
    return source, _sha256(archive_path)


def _iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _copy_new(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ReleaseError(f"refusing to overwrite existing release file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    now = time.time()
    os.utime(destination, (now, now))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _wheel_names(wheel: Path) -> list[str]:
    with ZipFile(wheel) as archive:
        return [name for name in archive.namelist() if not name.endswith("/")]


def _normalize_sdist(path: Path, epoch: int) -> None:
    """Rewrite setuptools' sdist with stable tar and gzip metadata."""

    with tarfile.open(path, "r:gz") as source:
        entries: list[tuple[tarfile.TarInfo, bytes | None]] = []
        for member in source.getmembers():
            content = None
            if member.isfile():
                handle = source.extractfile(member)
                if handle is None:
                    raise ReleaseError(f"cannot read sdist member: {member.name}")
                content = handle.read()
            entries.append((member, content))
    raw_tar = io.BytesIO()
    with tarfile.open(fileobj=raw_tar, mode="w", format=tarfile.PAX_FORMAT) as destination:
        for member, content in sorted(entries, key=lambda item: item[0].name):
            normalized = tarfile.TarInfo(member.name)
            normalized.type = member.type
            normalized.mode = member.mode
            normalized.linkname = member.linkname
            normalized.mtime = epoch
            normalized.uid = 0
            normalized.gid = 0
            normalized.uname = ""
            normalized.gname = ""
            normalized.size = len(content) if content is not None else 0
            destination.addfile(
                normalized,
                io.BytesIO(content) if content is not None else None,
            )
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as stream:
        stream.write(raw_tar.getvalue())
    path.write_bytes(compressed.getvalue())


def _validate_wheel(wheel: Path) -> None:
    names = _wheel_names(wheel)
    name_set = set(names)
    missing = sorted(REQUIRED_WHEEL_FILES - name_set)
    if missing:
        raise ReleaseError(f"Local wheel is missing required package data: {missing}")
    if not any(name.startswith(f"{PACKAGE}-") and name.endswith(".dist-info/METADATA") for name in names):
        raise ReleaseError("Local wheel is missing dist-info metadata")
    for name in names:
        path = Path(name)
        lower_name = name.lower()
        if any(component in _FORBIDDEN_WHEEL_COMPONENTS for component in path.parts):
            raise ReleaseError(f"forbidden generated/test path in wheel: {name}")
        if path.suffix.lower() == ".pyc":
            raise ReleaseError(f"bytecode in wheel: {name}")
        if path.suffix.lower() in _FORBIDDEN_DATABASE_SUFFIXES:
            raise ReleaseError(f"database in wheel: {name}")
        if (
            path.name.lower() in _FORBIDDEN_SECRET_NAMES
            or path.suffix.lower() in _FORBIDDEN_SECRET_SUFFIXES
            or ".env" in lower_name
        ):
            raise ReleaseError(f"secret/config artifact in wheel: {name}")
        if "build-copy" in path.parts:
            raise ReleaseError(f"build copy in wheel: {name}")


def _validate_license_files(archive: Path) -> None:
    if archive.suffix == ".whl":
        names = _wheel_names(archive)
    else:
        with tarfile.open(archive, "r:gz") as source:
            names = [member.name for member in source.getmembers()]
    present = {Path(name).name for name in names}
    missing = sorted(_LICENSE_FILE_NAMES - present)
    if missing:
        raise ReleaseError(f"release artifact is missing license files: {missing}")


def _build_distribution(source: Path, output: Path, env: dict[str, str]) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    _run(
        (
            sys.executable,
            "-m",
            "build",
            "--sdist",
            "--wheel",
            "--no-isolation",
            "--outdir",
            output,
            source,
        ),
        cwd=source,
        env=env,
    )
    wheels = sorted(output.glob("*.whl"))
    sdists = sorted(output.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseError(
            f"expected one wheel and one sdist, found {len(wheels)} wheels and {len(sdists)} sdists"
        )
    _normalize_sdist(sdists[0], int(env["SOURCE_DATE_EPOCH"]))
    _validate_wheel(wheels[0])
    _validate_license_files(wheels[0])
    _validate_license_files(sdists[0])
    return wheels[0], sdists[0]


def _package_name(spec: str) -> str:
    return re.split(r"[<>=!~;\s]", spec, maxsplit=1)[0].replace("_", "-").lower()


def _venv_python(venv: Path) -> Path:
    candidate = venv / "bin" / "python"
    if candidate.is_file():
        return candidate
    candidate = venv / "Scripts" / "python.exe"
    if candidate.is_file():
        return candidate
    raise ReleaseError(f"temporary virtual environment has no Python executable: {venv}")


def _smoke_install(
    *,
    wheel: Path,
    project_dir: Path,
    dependency_wheels: Sequence[Path],
    use_system_site_packages: bool,
    temporary: Path,
) -> dict[str, Any]:
    venv = temporary / "smoke-venv"
    command = [sys.executable, "-m", "venv"]
    if use_system_site_packages:
        command.append("--system-site-packages")
    command.append(str(venv))
    _run(command, cwd=temporary)
    python = _venv_python(venv)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"

    project = _project_manifest(project_dir)
    dependencies = [str(item) for item in project.get("project", {}).get("dependencies", [])]
    dependency_names = {
        _package_name(path.name.split("-", maxsplit=1)[0]) for path in dependency_wheels
    }
    unresolved = [
        spec for spec in dependencies if _package_name(spec) not in dependency_names
    ]
    if unresolved:
        _run(
            (python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *unresolved),
            cwd=temporary,
            env=environment,
        )
    if dependency_wheels:
        _run(
            (
                python,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--no-deps",
                *(str(path) for path in dependency_wheels),
            ),
            cwd=temporary,
            env=environment,
        )
    _run(
        (
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-deps",
            wheel,
        ),
        cwd=temporary,
        env=environment,
    )
    imports = "; ".join(f"importlib.import_module({name!r})" for name in REQUIRED_IMPORTS)
    _run((python, "-c", f"import importlib; {imports}"), cwd=temporary, env=environment)
    _run((python, "-m", "ledgermind_local.cli", "--help"), cwd=temporary, env=environment)
    return {
        "passed": True,
        "imports": list(REQUIRED_IMPORTS),
        "cli": "python -m ledgermind_local.cli --help",
        "venv": "temporary isolated virtualenv",
        "system_site_packages": use_system_site_packages,
    }


def _artifact_records(output: Path, names: Iterable[str]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    records: list[dict[str, Any]] = []
    digests: dict[str, str] = {}
    for name in sorted(names):
        path = output / name
        if not path.is_file():
            raise ReleaseError(f"release artifact is missing: {path}")
        digest = _sha256(path)
        records.append({"name": name, "sha256": digest, "size_bytes": path.stat().st_size})
        digests[name] = digest
    if not records:
        raise ReleaseError("release contains no artifacts")
    return records, digests


def _manifest_path(args: argparse.Namespace, version: str, commit: str) -> Path:
    if args.manifest:
        return Path(args.manifest).expanduser().resolve()
    if args.output:
        return Path(args.output).expanduser().resolve() / MANIFEST_NAME
    return (
        Path(tempfile.gettempdir())
        / "ledgermind-releases"
        / COMPONENT
        / f"{version}-{commit[:12]}"
        / MANIFEST_NAME
    )


def build(args: argparse.Namespace) -> Path:
    commit, commit_epoch = _git_state(ROOT)
    version = _version(ROOT)
    _cleanup_generated(ROOT)
    _git_state(ROOT)
    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _manifest_path(args, version, commit).parent
    )
    if output.exists() and any(output.iterdir()):
        raise ReleaseError(f"release output must be empty or absent: {output}")
    dependency_wheels = tuple(Path(item).expanduser().resolve() for item in args.dependency_wheel)
    for dependency in dependency_wheels:
        if not dependency.is_file():
            raise ReleaseError(f"dependency wheel does not exist: {dependency}")

    build_epoch = time.time()
    with tempfile.TemporaryDirectory(prefix="ledgermind-local-release-") as temporary_name:
        temporary = Path(temporary_name)
        source, source_archive_sha256 = _archive_checkout(ROOT, temporary)
        environment = os.environ.copy()
        environment["SOURCE_DATE_EPOCH"] = str(commit_epoch)
        environment["PYTHONHASHSEED"] = "0"
        staged = temporary / "artifacts"
        wheel, sdist = _build_distribution(source, staged, environment)
        smoke = _smoke_install(
            wheel=wheel,
            project_dir=source,
            dependency_wheels=dependency_wheels,
            use_system_site_packages=args.system_site_packages,
            temporary=temporary,
        )
        output.mkdir(parents=True, exist_ok=True)
        copied_names: list[str] = []
        for artifact in (wheel, sdist):
            destination = output / artifact.name
            _copy_new(artifact, destination)
            copied_names.append(destination.name)

    records, digests = _artifact_records(output, copied_names)
    manifest = {
        "format": "ledgermind-release-manifest",
        "schema_version": 1,
        "component": COMPONENT,
        "source_commit": commit,
        "commit_sha": commit,
        "source_commit_timestamp": commit_epoch,
        "source_archive_sha256": source_archive_sha256,
        "version": version,
        "artifacts": records,
        "sha256": digests,
        "python_version": sys.version,
        "python_executable": sys.executable,
        "toolchain": {
            "python": sys.version,
            "pip": _run((sys.executable, "-m", "pip", "--version"), cwd=ROOT).stdout.strip(),
            "build": _run((sys.executable, "-m", "build", "--version"), cwd=ROOT).stdout.strip(),
        },
        "built_at_utc": _iso_utc(build_epoch),
        "build_time_utc": _iso_utc(build_epoch),
        "build_time_epoch": build_epoch,
        "checks": {
            "clean_tracked_source": True,
            "wheel_contents": True,
            "license_files": True,
            "install_smoke": True,
            "cli_help": True,
        },
        "install_smoke": smoke,
    }
    manifest_path = output / MANIFEST_NAME
    _write_json(manifest_path, manifest)
    _cleanup_generated(ROOT)
    _assert_no_generated(ROOT)
    _git_state(ROOT)
    print(manifest_path)
    return manifest_path


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReleaseError(f"release manifest is required: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot read release manifest: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseError("release manifest must contain a JSON object")
    return value


def verify(args: argparse.Namespace) -> Path:
    commit = _git(ROOT, "rev-parse", "HEAD")
    commit_epoch = int(_git(ROOT, "show", "-s", "--format=%ct", "HEAD"))
    version = _version(ROOT)
    path = _manifest_path(args, version, commit)
    manifest = _load_manifest(path)
    if manifest.get("format") != "ledgermind-release-manifest":
        raise ReleaseError("unsupported release manifest format")
    if manifest.get("schema_version") != 1:
        raise ReleaseError("unsupported release manifest schema version")
    if manifest.get("component") != COMPONENT:
        raise ReleaseError("manifest component does not match Local")
    if manifest.get("source_commit") != commit or manifest.get("commit_sha") != commit:
        raise ReleaseError("manifest source commit does not match current HEAD")
    if manifest.get("version") != version:
        raise ReleaseError("manifest version does not match pyproject.toml")
    build_epoch = manifest.get("build_time_epoch")
    if not isinstance(build_epoch, (int, float)) or build_epoch < commit_epoch:
        raise ReleaseError("manifest was created before the current source commit")
    smoke = manifest.get("install_smoke")
    if not isinstance(smoke, dict) or smoke.get("passed") is not True:
        raise ReleaseError("manifest does not prove install smoke passed")
    checks = manifest.get("checks")
    if not isinstance(checks, dict) or checks.get("license_files") is not True:
        raise ReleaseError("manifest does not prove license files were packaged")
    records = manifest.get("artifacts")
    digest_map = manifest.get("sha256")
    if not isinstance(records, list) or not records or not isinstance(digest_map, dict):
        raise ReleaseError("manifest must list artifacts and SHA-256 digests")
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("name"), str):
            raise ReleaseError("manifest contains an invalid artifact record")
        name = record["name"]
        if Path(name).name != name:
            raise ReleaseError("manifest artifact path must be a file name")
        artifact = path.parent / name
        if not artifact.is_file():
            raise ReleaseError(f"manifest artifact is missing: {artifact}")
        digest = _sha256(artifact)
        if digest != record.get("sha256") or digest_map.get(name) != digest:
            raise ReleaseError(f"SHA-256 mismatch for release artifact: {name}")
        if artifact.stat().st_mtime + 1 < commit_epoch:
            raise ReleaseError(f"artifact predates current source commit: {name}")
    _cleanup_generated(ROOT)
    _assert_no_generated(ROOT)
    print(path)
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"), nargs="?", default="build")
    parser.add_argument("--output", type=Path, help="external release output directory")
    parser.add_argument("--manifest", type=Path, help="manifest to verify")
    parser.add_argument(
        "--dependency-wheel",
        action="append",
        default=[],
        help="wheel for an unpublished sibling dependency (repeatable)",
    )
    parser.add_argument(
        "--system-site-packages",
        action="store_true",
        help="allow the temporary smoke venv to see host runtime dependencies",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "build":
            build(args)
        else:
            verify(args)
    except (ReleaseError, OSError, subprocess.SubprocessError) as exc:
        print(f"release failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
