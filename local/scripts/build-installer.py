#!/usr/bin/env python3
"""Build a self-contained installer launcher without contacting PyPI.

The release job supplies a bundle containing the Python runtime and its
dependencies.  This script only creates the stable, executable entry point.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="build LedgerMind installer launcher")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--source", type=Path, required=True, help="bundle Python source root"
    )
    parser.add_argument(
        "--extra-source",
        type=Path,
        action="append",
        default=[],
        help=(
            "additional current source root copied beside --source; use for "
            "runtime packages such as integrations and protocol"
        ),
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="runtime executable recorded in launcher",
    )
    parser.add_argument(
        "--public-key", type=Path, help="embedded raw Ed25519 public key"
    )
    parser.add_argument(
        "--site-packages",
        type=Path,
        action="append",
        default=[],
        help="prebuilt dependency directory; never downloaded by this script",
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        help="prebuilt Python runtime root for a self-extracting launcher",
    )
    parser.add_argument(
        "--runtime-executable",
        default="bin/python3",
        help="runtime executable relative to --runtime-root",
    )
    return parser


def _ignore_build_files(_path: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
    }


def _copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=_ignore_build_files, dirs_exist_ok=True)


def _copy_dependencies(sources: list[Path], target: Path) -> None:
    for dependency_source in sources:
        dependency_source = dependency_source.expanduser().resolve()
        if not dependency_source.is_dir():
            raise SystemExit(
                f"site-packages directory does not exist: {dependency_source}"
            )
        _copy_tree(dependency_source, target)


def _payload_archive(payload_root: Path) -> bytes:
    archive_bytes = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=archive_bytes, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for path in sorted(payload_root.rglob("*")):
            relative = path.relative_to(payload_root)
            info = archive.gettarinfo(str(path), arcname=str(relative))
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            if path.is_file() and not path.is_symlink():
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
            else:
                archive.addfile(info)
    return archive_bytes.getvalue()


def _self_extracting_launcher(
    *, payload_id: str, runtime_executable: str, public_key: str
) -> str:
    key_export = ""
    if public_key:
        key_export = f"export LEDGERMIND_INSTALLER_PUBLIC_KEY='{public_key}'\n"
    return f"""#!/bin/sh
set -eu
umask 077

cache_root=${{XDG_CACHE_HOME:-${{HOME:-/tmp}}/.cache}}
payload_parent="$cache_root/ledgermind/installer"
payload_root="$payload_parent/{payload_id}"
runtime="$payload_root/runtime/{runtime_executable}"
if [ ! -x "$runtime" ]; then
  temporary="$payload_parent/.{payload_id}.$$"
  cleanup() {{ rm -rf "$temporary"; }}
  trap cleanup EXIT INT TERM
  mkdir -p "$payload_parent" "$temporary"
  payload_line=$(awk '/^__LEDGERMIND_PAYLOAD_BELOW__$/ {{ print NR + 1; exit }}' "$0")
  if [ -z "$payload_line" ]; then
    printf '%s\\n' 'installer payload marker is missing' >&2
    exit 6
  fi
  tail -n +"$payload_line" "$0" | tar -xzf - -C "$temporary"
  if [ ! -x "$temporary/runtime/{runtime_executable}" ]; then
    printf '%s\\n' 'bundled Python runtime is missing' >&2
    exit 6
  fi
  if [ -e "$payload_root" ]; then
    rm -rf "$payload_root"
  fi
  mv "$temporary" "$payload_root"
  trap - EXIT INT TERM
fi
{key_export}export PYTHONPATH="$payload_root/python:$payload_root/python/site-packages${{PYTHONPATH:+:$PYTHONPATH}}"
exec "$runtime" -m ledgermind_local.installer.cli "$@"

__LEDGERMIND_PAYLOAD_BELOW__
"""


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = args.source.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"source directory does not exist: {source}")
    extra_sources = [item.expanduser().resolve() for item in args.extra_source]
    missing_extra = next((item for item in extra_sources if not item.is_dir()), None)
    if missing_extra is not None:
        raise SystemExit(f"extra source directory does not exist: {missing_extra}")
    output = args.output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    target_source = output.parent / "python"
    if target_source.exists():
        shutil.rmtree(target_source)
    runtime_root = (
        args.runtime_root.expanduser().resolve() if args.runtime_root else None
    )
    runtime_executable = Path(args.runtime_executable)
    if runtime_executable.is_absolute() or ".." in runtime_executable.parts:
        raise SystemExit("runtime executable must be relative to --runtime-root")
    if runtime_root is not None and not (runtime_root / runtime_executable).is_file():
        raise SystemExit(
            "bundled runtime executable does not exist: "
            f"{runtime_root / runtime_executable}"
        )
    payload = {
        "schema_version": 1,
        "python": str(args.python),
        "module": "ledgermind_local.installer.cli",
        "source": "embedded" if runtime_root is not None else str(source),
        "self_contained": runtime_root is not None,
    }
    public_key = ""
    if args.public_key is not None:
        raw_key = args.public_key.expanduser().read_bytes().strip()
        if len(raw_key) != 32:
            raise SystemExit("public key must contain 32 raw bytes")
        public_key = base64.b64encode(raw_key).decode("ascii")
        payload["public_key_fingerprint"] = hashlib.sha256(raw_key).hexdigest()
    if runtime_root is None:
        # The launcher is intentionally plain text.  The release manifest signs
        # its exact bytes; no installer logic is hidden in shell.
        launcher = f"""#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

META = {payload!r}
_LOCATION = Path(__file__).resolve().parent
SOURCE = _LOCATION / "python"
if not SOURCE.is_dir():
    SOURCE = _LOCATION.parent / "python"
sys.path.insert(0, str(SOURCE / "site-packages"))
sys.path.insert(0, str(SOURCE))
if {public_key!r}:
    os.environ.setdefault("LEDGERMIND_INSTALLER_PUBLIC_KEY", {public_key!r})
from ledgermind_local.installer.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
        _copy_tree(source, target_source)
        for extra_source in extra_sources:
            _copy_tree(extra_source, target_source)
        _copy_dependencies(args.site_packages, target_source / "site-packages")
        staging = output.with_name(f".{output.name}.tmp")
        staging.write_text(launcher, encoding="utf-8")
        os.chmod(staging, 0o700)
        staging.replace(output)
    else:
        with tempfile.TemporaryDirectory(prefix="ledgermind-installer-") as temporary:
            payload_root = Path(temporary) / "payload"
            _copy_tree(source, payload_root / "python")
            for extra_source in extra_sources:
                _copy_tree(extra_source, payload_root / "python")
            _copy_dependencies(
                args.site_packages, payload_root / "python" / "site-packages"
            )
            _copy_tree(runtime_root, payload_root / "runtime")
            archive = _payload_archive(payload_root)
            payload_id = hashlib.sha256(archive).hexdigest()[:32]
            launcher = _self_extracting_launcher(
                payload_id=payload_id,
                runtime_executable=runtime_executable.as_posix(),
                public_key=public_key,
            ).encode("utf-8")
            staging = output.with_name(f".{output.name}.tmp")
            with staging.open("wb") as handle:
                handle.write(launcher)
                handle.write(archive)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(staging, 0o700)
            staging.replace(output)
            payload = {
                **payload,
                "payload_sha256": hashlib.sha256(archive).hexdigest(),
                "runtime_executable": runtime_executable.as_posix(),
            }
    os.chmod(output, 0o700)
    metadata = output.with_suffix(output.suffix + ".json")
    metadata.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    os.chmod(metadata, 0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
