#!/usr/bin/env python3
"""Build and verify clean Integrations and Protocol Python releases.

Both projects are built from one tracked ``git archive HEAD`` in an external
workspace.  Wheel contents are checked, both distributions are installed in a
fresh temporary environment, Hermes CLI/runtime smoke tests run from the
installed packages, and only then are artifacts copied to the external output
with a commit-bound manifest.
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
COMPONENT = "ledgermind-integrations"
MANIFEST_NAME = f"{COMPONENT}-manifest.json"
PROTOCOL_PROJECT = Path("protocol/python")
INTEGRATIONS_PROJECT = Path("python")
PROTOCOL_PACKAGE = "ledgermind_protocol"
INTEGRATIONS_PACKAGE = "ledgermind_integrations"
PROTOCOL_REQUIRED_WHEEL_FILES = {
    "ledgermind_protocol/__init__.py",
    "ledgermind_protocol/canonical.py",
    "ledgermind_protocol/context.py",
    "ledgermind_protocol/core_ipc.py",
    "ledgermind_protocol/models.py",
    "ledgermind_protocol/object_facet.py",
    "ledgermind_protocol/resolution.py",
    "ledgermind_protocol/validation.py",
    "ledgermind_protocol/py.typed",
}
INTEGRATIONS_REQUIRED_WHEEL_FILES = {
    "ledgermind_integrations/__init__.py",
    "ledgermind_integrations/py.typed",
    "ledgermind_integrations/adapters/lifecycle/__init__.py",
    "ledgermind_integrations/adapters/lifecycle/bridge.py",
    "ledgermind_integrations/adapters/lifecycle/config.py",
    "ledgermind_integrations/adapters/hermes/plugin.yaml",
    "ledgermind_integrations/adapters/hermes/plugin_entry.py",
    "ledgermind_integrations/adapters/hermes/runtime.py",
    "ledgermind_integrations/adapters/hermes/round_capture.py",
    "ledgermind_integrations/runtime/client.py",
    "ledgermind_integrations/runtime/delivery.py",
    "ledgermind_integrations/runtime/spool.py",
    "ledgermind_integrations/runtime/spool_migration.py",
    "ledgermind_integrations/runtime/worker_loop.py",
}
REQUIRED_SOURCE_ASSETS = {
    Path("schemas/raw-round.schema.json"),
    Path("schemas/core-ipc/object-facet/raw-round-resolution.schema.json"),
    Path("conformance/valid/hermes_complete.json"),
    Path("conformance/digests/raw_round.json"),
    Path("conformance/object-facet/digests.json"),
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


def _project_manifest(project: Path) -> dict[str, Any]:
    with (project / "pyproject.toml").open("rb") as handle:
        value = tomllib.load(handle)
    if not isinstance(value, dict):
        raise ReleaseError(f"{project}/pyproject.toml must contain a TOML table")
    return value


def _project_name_version(project: Path) -> tuple[str, str]:
    metadata = _project_manifest(project).get("project", {})
    name = metadata.get("name")
    version = metadata.get("version")
    if not isinstance(name, str) or not name:
        raise ReleaseError(f"{project}/pyproject.toml does not define project.name")
    if not isinstance(version, str) or not version:
        raise ReleaseError(f"{project}/pyproject.toml does not define project.version")
    return name, version


def _cleanup_generated(root: Path) -> None:
    """Remove only known build/test artifacts, never arbitrary user files."""

    for current, directories, files in os.walk(root, topdown=True):
        current_path = Path(current)
        if ".git" in current_path.parts:
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
        if ".git" in current_path.parts:
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


def _validate_wheel(wheel: Path, package: str, required: set[str]) -> None:
    names = _wheel_names(wheel)
    name_set = set(names)
    missing = sorted(required - name_set)
    if missing:
        raise ReleaseError(f"{package} wheel is missing required package data: {missing}")
    if package == "ledgermind-protocol":
        unstable_modules = sorted(
            name for name in names if Path(name).name.startswith("object_facet_")
        )
        if unstable_modules:
            raise ReleaseError(
                f"{package} wheel contains unstable object-facet modules: {unstable_modules}"
            )
    normalized = package.replace("-", "_")
    if not any(name.startswith(f"{normalized}-") and name.endswith(".dist-info/METADATA") for name in names):
        raise ReleaseError(f"{package} wheel is missing dist-info metadata")
    metadata_roots = {
        Path(name).parts[0]
        for name in names
        if Path(name).parts
        and Path(name).parts[0].startswith(f"{normalized}-")
        and Path(name).parts[0].endswith(".dist-info")
    }
    package_root = f"{normalized}/"
    outside_boundary = [
        name
        for name in names
        if not name.startswith(package_root) and Path(name).parts[0] not in metadata_roots
    ]
    if outside_boundary:
        raise ReleaseError(f"unexpected public package path in wheel: {outside_boundary}")
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


def _validate_sdist(sdist: Path, package: str, required: set[str]) -> None:
    with tarfile.open(sdist, "r:gz") as archive:
        names = [member.name for member in archive.getmembers()]
    roots = {Path(name).parts[0] for name in names if Path(name).parts}
    if len(roots) != 1:
        raise ReleaseError(f"{package} sdist must have one top-level directory")
    root = next(iter(roots))
    required_names = {"pyproject.toml", *(f"src/{name}" for name in required)}
    missing = sorted(f"{root}/{name}" for name in required_names if f"{root}/{name}" not in names)
    if missing:
        raise ReleaseError(f"{package} sdist is missing required source files: {missing}")
    if package == "ledgermind-protocol":
        unstable_modules = sorted(
            name for name in names if Path(name).name.startswith("object_facet_")
        )
        if unstable_modules:
            raise ReleaseError(
                f"{package} sdist contains unstable object-facet modules: {unstable_modules}"
            )
    for name in names:
        path = Path(name)
        lower_name = name.lower()
        if any(component in _GENERATED_DIR_NAMES for component in path.parts[1:]):
            raise ReleaseError(f"generated path in sdist: {name}")
        if path.suffix.lower() in _GENERATED_FILE_SUFFIXES:
            raise ReleaseError(f"bytecode in sdist: {name}")
        if path.suffix.lower() in _FORBIDDEN_DATABASE_SUFFIXES:
            raise ReleaseError(f"database in sdist: {name}")
        if (
            path.name.lower() in _FORBIDDEN_SECRET_NAMES
            or path.suffix.lower() in _FORBIDDEN_SECRET_SUFFIXES
            or ".env" in lower_name
        ):
            raise ReleaseError(f"secret/config artifact in sdist: {name}")


def _validate_license_files(archive: Path, package: str) -> None:
    if archive.suffix == ".whl":
        names = _wheel_names(archive)
    else:
        with tarfile.open(archive, "r:gz") as source:
            names = [member.name for member in source.getmembers()]
    present = {Path(name).name for name in names}
    missing = sorted(_LICENSE_FILE_NAMES - present)
    if missing:
        raise ReleaseError(f"{package} release artifact is missing license files: {missing}")


def _build_distribution(
    project_source: Path,
    output: Path,
    env: dict[str, str],
    package: str,
    required: set[str],
) -> tuple[Path, Path]:
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
            project_source,
        ),
        cwd=project_source,
        env=env,
    )
    wheels = sorted(output.glob("*.whl"))
    sdists = sorted(output.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseError(
            f"{package}: expected one wheel and one sdist, found "
            f"{len(wheels)} wheels and {len(sdists)} sdists"
        )
    _normalize_sdist(sdists[0], int(env["SOURCE_DATE_EPOCH"]))
    _validate_wheel(wheels[0], package, required)
    _validate_sdist(sdists[0], package, required)
    _validate_license_files(wheels[0], package)
    _validate_license_files(sdists[0], package)
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
    protocol_project: Path,
    integrations_project: Path,
    protocol_wheel: Path,
    integrations_wheel: Path,
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

    dependencies: list[str] = []
    for project in (protocol_project, integrations_project):
        project_dependencies = _project_manifest(project).get("project", {}).get("dependencies", [])
        for spec in project_dependencies:
            text = str(spec)
            if _package_name(text) == "ledgermind-protocol":
                continue
            if _package_name(text) not in {_package_name(item) for item in dependencies}:
                dependencies.append(text)
    if dependencies:
        _run(
            (python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *dependencies),
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
            protocol_wheel,
            integrations_wheel,
        ),
        cwd=temporary,
        env=environment,
    )
    _run(
        (
            python,
            "-c",
            (
                "import importlib, inspect; "
                "importlib.import_module('ledgermind_protocol'); "
                "lifecycle = importlib.import_module('ledgermind_integrations.adapters.lifecycle'); "
                "runtime = importlib.import_module('ledgermind_integrations.adapters.hermes.runtime'); "
                "migration = importlib.import_module('ledgermind_integrations.runtime.spool_migration'); "
                "assert hasattr(lifecycle, 'handle_hook'); "
                "assert hasattr(lifecycle, 'load_lifecycle_config'); "
                "assert hasattr(runtime, 'ActiveRoundState'); "
                "assert hasattr(runtime.HermesPluginRuntime, 'finish_session'); "
                "assert hasattr(migration, 'migrate_spool'); "
                "assert 'active_rounds' in inspect.getsource(runtime.HermesPluginRuntime)"
            ),
        ),
        cwd=temporary,
        env=environment,
    )
    _run((python, "-m", "ledgermind_integrations.cli", "--help"), cwd=temporary, env=environment)
    entrypoint = python.parent / "ledgermind-integrations"
    if entrypoint.is_file():
        _run((entrypoint, "--help"), cwd=temporary, env=environment)
    return {
        "passed": True,
        "imports": [
            "ledgermind_protocol",
            "ledgermind_integrations.adapters.lifecycle.handle_hook",
            "ledgermind_integrations.adapters.lifecycle.load_lifecycle_config",
            "ledgermind_integrations.adapters.hermes.runtime.ActiveRoundState",
            "ledgermind_integrations.adapters.hermes.runtime.HermesPluginRuntime.finish_session",
            "ledgermind_integrations.runtime.spool_migration.migrate_spool",
            "active_rounds correlation state",
        ],
        "cli": [
            "python -m ledgermind_integrations.cli --help",
            "ledgermind-integrations --help",
        ],
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
    integrations_name, integrations_version = _project_name_version(ROOT / INTEGRATIONS_PROJECT)
    protocol_name, protocol_version = _project_name_version(ROOT / PROTOCOL_PROJECT)
    if integrations_name != COMPONENT or protocol_name != "ledgermind-protocol":
        raise ReleaseError("unexpected project names in Integrations workspace")
    for asset in REQUIRED_SOURCE_ASSETS:
        if not (ROOT / asset).is_file():
            raise ReleaseError(f"required schema/conformance asset is missing: {ROOT / asset}")
    _cleanup_generated(ROOT)
    _git_state(ROOT)
    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _manifest_path(args, integrations_version, commit).parent
    )
    if output.exists() and any(output.iterdir()):
        raise ReleaseError(f"release output must be empty or absent: {output}")

    build_epoch = time.time()
    with tempfile.TemporaryDirectory(prefix="ledgermind-integrations-release-") as temporary_name:
        temporary = Path(temporary_name)
        source, source_archive_sha256 = _archive_checkout(ROOT, temporary)
        environment = os.environ.copy()
        environment["SOURCE_DATE_EPOCH"] = str(commit_epoch)
        environment["PYTHONHASHSEED"] = "0"
        staged = temporary / "artifacts"
        protocol_wheel, protocol_sdist = _build_distribution(
            source / PROTOCOL_PROJECT,
            staged / "protocol",
            environment,
            "ledgermind-protocol",
            PROTOCOL_REQUIRED_WHEEL_FILES,
        )
        integrations_wheel, integrations_sdist = _build_distribution(
            source / INTEGRATIONS_PROJECT,
            staged / "integrations",
            environment,
            COMPONENT,
            INTEGRATIONS_REQUIRED_WHEEL_FILES,
        )
        smoke = _smoke_install(
            protocol_project=source / PROTOCOL_PROJECT,
            integrations_project=source / INTEGRATIONS_PROJECT,
            protocol_wheel=protocol_wheel,
            integrations_wheel=integrations_wheel,
            use_system_site_packages=args.system_site_packages,
            temporary=temporary,
        )
        output.mkdir(parents=True, exist_ok=True)
        copied_names: list[str] = []
        for artifact in (protocol_wheel, protocol_sdist, integrations_wheel, integrations_sdist):
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
        "version": integrations_version,
        "versions": {
            "ledgermind-integrations": integrations_version,
            "ledgermind-protocol": protocol_version,
        },
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
            "protocol_wheel_contents": True,
            "integrations_wheel_contents": True,
            "license_files": True,
            "schema_and_conformance_assets": True,
            "install_smoke": True,
            "cli_help": True,
            "hermes_active_round_runtime": True,
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
    commit, commit_epoch = _git_state(ROOT)
    integrations_name, integrations_version = _project_name_version(ROOT / INTEGRATIONS_PROJECT)
    protocol_name, protocol_version = _project_name_version(ROOT / PROTOCOL_PROJECT)
    if integrations_name != COMPONENT or protocol_name != "ledgermind-protocol":
        raise ReleaseError("unexpected project names in Integrations workspace")
    path = _manifest_path(args, integrations_version, commit)
    manifest = _load_manifest(path)
    if manifest.get("format") != "ledgermind-release-manifest":
        raise ReleaseError("manifest format is not supported")
    if manifest.get("schema_version") != 1:
        raise ReleaseError("manifest schema_version is not supported")
    if manifest.get("component") != COMPONENT:
        raise ReleaseError("manifest component does not match Integrations")
    if manifest.get("source_commit") != commit or manifest.get("commit_sha") != commit:
        raise ReleaseError("manifest source commit does not match current HEAD")
    if manifest.get("version") != integrations_version:
        raise ReleaseError("manifest version does not match integrations pyproject.toml")
    versions = manifest.get("versions")
    if not isinstance(versions, dict):
        raise ReleaseError("manifest must record both package versions")
    if versions.get("ledgermind-protocol") != protocol_version:
        raise ReleaseError("manifest protocol version does not match protocol pyproject.toml")
    build_epoch = manifest.get("build_time_epoch")
    if not isinstance(build_epoch, (int, float)) or build_epoch < commit_epoch:
        raise ReleaseError("manifest was created before the current source commit")
    source_archive_sha256 = manifest.get("source_archive_sha256")
    if not isinstance(source_archive_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_archive_sha256):
        raise ReleaseError("manifest must record the source archive SHA-256")
    checks = manifest.get("checks")
    required_checks = {
        "clean_tracked_source",
        "protocol_wheel_contents",
        "integrations_wheel_contents",
        "schema_and_conformance_assets",
        "install_smoke",
        "cli_help",
        "hermes_active_round_runtime",
        "license_files",
    }
    if not isinstance(checks, dict) or any(checks.get(name) is not True for name in required_checks):
        raise ReleaseError("manifest does not contain all successful release checks")
    smoke = manifest.get("install_smoke")
    if not isinstance(smoke, dict) or smoke.get("passed") is not True:
        raise ReleaseError("manifest does not prove install smoke passed")
    records = manifest.get("artifacts")
    digest_map = manifest.get("sha256")
    if not isinstance(records, list) or not records or not isinstance(digest_map, dict):
        raise ReleaseError("manifest must list artifacts and SHA-256 digests")
    artifact_names: list[str] = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("name"), str):
            raise ReleaseError("manifest contains an invalid artifact record")
        name = record["name"]
        if Path(name).name != name:
            raise ReleaseError("manifest artifact path must be a file name")
        if name in artifact_names:
            raise ReleaseError(f"manifest contains duplicate artifact: {name}")
        artifact_names.append(name)
        artifact = path.parent / name
        if not artifact.is_file():
            raise ReleaseError(f"manifest artifact is missing: {artifact}")
        digest = _sha256(artifact)
        if digest != record.get("sha256") or digest_map.get(name) != digest:
            raise ReleaseError(f"SHA-256 mismatch for release artifact: {name}")
        if record.get("size_bytes") != artifact.stat().st_size:
            raise ReleaseError(f"size mismatch for release artifact: {name}")
        if artifact.stat().st_mtime + 1 < commit_epoch:
            raise ReleaseError(f"artifact predates current source commit: {name}")
    expected_sdists = {
        f"{integrations_name.replace('-', '_')}-{integrations_version}.tar.gz",
        f"{protocol_name.replace('-', '_')}-{protocol_version}.tar.gz",
    }
    if not expected_sdists.issubset(artifact_names):
        raise ReleaseError("manifest is missing a protocol or integrations sdist")
    for name, version in (
        (integrations_name, integrations_version),
        (protocol_name, protocol_version),
    ):
        normalized = name.replace("-", "_")
        if not any(
            artifact.startswith(f"{normalized}-{version}-") and artifact.endswith(".whl")
            for artifact in artifact_names
        ):
            raise ReleaseError(f"manifest is missing the {name} wheel")
    _cleanup_generated(ROOT)
    _assert_no_generated(ROOT)
    _git_state(ROOT)
    print(path)
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"), nargs="?", default="build")
    parser.add_argument("--output", type=Path, help="external release output directory")
    parser.add_argument("--manifest", type=Path, help="manifest to verify")
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
