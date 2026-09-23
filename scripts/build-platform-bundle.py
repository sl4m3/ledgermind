#!/usr/bin/env python3
"""Build a versioned platform bundle with a deterministic manifest.

No dependency resolver is invoked.  The caller supplies already-built Core,
Local, Integrations, and embedding runtime artifacts.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="build LedgerMind platform bundle")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-version", required=True)
    parser.add_argument(
        "--platform", choices=("linux-x86_64", "linux-aarch64"), required=True
    )
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--local-source", type=Path, required=True)
    parser.add_argument("--integrations-source", type=Path, required=True)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--site-packages", type=Path, action="append", default=[])
    parser.add_argument(
        "--python-runtime",
        type=Path,
        help="CPython runtime root containing bin/python3.12",
    )
    parser.add_argument("--embedding-runtime-cpu", type=Path)
    parser.add_argument("--embedding-runtime-cuda", type=Path)
    parser.add_argument("--embedding-runtime-rocm", type=Path)
    parser.add_argument("--protocol-schemas", type=Path)
    parser.add_argument("--protocol-python", type=Path)
    parser.add_argument("--embedding-catalog", type=Path)
    parser.add_argument("--hardware-gate-evidence", type=Path)
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_source(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(
            source,
            target,
            ignore=lambda _path, names: {
                name
                for name in names
                if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
            },
            dirs_exist_ok=True,
        )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _protocol_package(source: Path | None) -> Path:
    if source is None:
        raise SystemExit(
            "Hermes integration requires --protocol-python for a self-contained payload"
        )
    candidates = (source / "ledgermind_protocol", source / "src" / "ledgermind_protocol")
    package = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if package is None:
        raise SystemExit(f"ledgermind_protocol package does not exist under: {source}")
    return package


def _copy_hermes_plugin(
    source: Path, target: Path, *, protocol_python: Path | None
) -> None:
    """Accept either a prepared plugin payload or the Hermes package source."""

    if (source / "_vendor" / "ledgermind_integrations").is_dir():
        _copy_source(source, target)
        return
    if (source / "plugin.yaml").is_file() and (source / "plugin_entry.py").is_file():
        target.mkdir(parents=True, exist_ok=True)
        _copy_source(source / "plugin.yaml", target / "plugin.yaml")
        package_root = source.parents[1]
        if package_root.name != "ledgermind_integrations":
            raise SystemExit(
                "Hermes package source must be inside ledgermind_integrations/adapters"
            )
        _copy_source(
            package_root, target / "_vendor" / "ledgermind_integrations"
        )
        _copy_source(
            _protocol_package(protocol_python),
            target / "_vendor" / "ledgermind_protocol",
        )
        (target / "__init__.py").write_text(
            "import sys\n"
            "from pathlib import Path\n\n"
            "_VENDOR = Path(__file__).resolve().parent / '_vendor'\n"
            "if str(_VENDOR) not in sys.path:\n"
            "    sys.path.insert(0, str(_VENDOR))\n\n"
            "from ledgermind_integrations.adapters.hermes.plugin_entry import register\n\n"
            '__all__ = ["register"]\n',
            encoding="utf-8",
        )
        return
    _copy_source(source, target)


def _integration_source(root: Path, target: str) -> Path:
    """Resolve both the legacy Hermes path and the new adapters-root input."""

    candidate = root / target
    if candidate.is_dir():
        return candidate
    if target == "hermes":
        return root
    sibling = root.parent / target
    if sibling.is_dir():
        return sibling
    raise SystemExit(f"{target} integration payload does not exist under: {root}")


def _private_key(path: Path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    raw = path.read_bytes().strip()
    if len(raw) != 32:
        try:
            raw = base64.b64decode(raw, validate=True)
        except (ValueError, UnicodeError):
            raw = bytes.fromhex(raw.decode("ascii"))
    if len(raw) != 32:
        raise SystemExit("Ed25519 signing key must contain 32 raw bytes")
    return Ed25519PrivateKey.from_private_bytes(raw)


def _public_key_bytes(path: Path) -> bytes:
    raw = path.read_bytes().strip()
    if len(raw) == 32:
        return raw
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (ValueError, UnicodeError):
        decoded = b""
    if len(decoded) == 32:
        return decoded
    try:
        decoded = bytes.fromhex(raw.decode("ascii"))
    except (UnicodeError, ValueError) as exc:
        raise SystemExit("Ed25519 public key must be raw, base64, or hex") from exc
    if len(decoded) != 32:
        raise SystemExit("Ed25519 public key must contain 32 bytes")
    return decoded


def _copy_runtime(source: Path | None, target: Path, *, device: str) -> None:
    if source is None:
        return
    source = source.expanduser()
    if not source.is_dir():
        raise SystemExit(f"{device} embedding runtime does not exist: {source}")
    _copy_source(source, target)


def _public_bytes(key: Any) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.expanduser()
    if output.exists():
        raise SystemExit(f"output already exists: {output}")
    bundle = output / "bundle"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "signatures").mkdir()
    for integration in ("hermes", "opencode", "openclaw"):
        (bundle / "integrations" / integration).mkdir(parents=True)
    (bundle / "protocol" / "schemas").mkdir(parents=True)
    (bundle / "protocol" / "python").mkdir(parents=True)
    (bundle / "defaults").mkdir()
    (bundle / "LICENSES").mkdir()
    for device in ("cpu", "cuda", "rocm"):
        (bundle / "embedding-runtimes" / device).mkdir(parents=True)
    (bundle / "defaults" / "config.json").write_text(
        '{"schema_version":2,"integrations":[]}\n', encoding="utf-8"
    )
    (bundle / "defaults" / "facets.json").write_text("[]\n", encoding="utf-8")
    (bundle / "defaults" / "logging.json").write_text(
        '{"level":"INFO"}\n', encoding="utf-8"
    )

    core = args.core.expanduser()
    if not core.is_file():
        raise SystemExit(f"Core artifact does not exist: {core}")
    _copy_source(core, bundle / "bin" / "ledgermind-core")
    installer = args.installer.expanduser()
    if not installer.is_file():
        raise SystemExit(f"installer artifact does not exist: {installer}")
    _copy_source(installer, bundle / "bin" / "ledgermind")
    os.chmod(bundle / "bin" / "ledgermind", 0o700)
    for suffix in (".sig", ".pub"):
        candidate = core.with_name(core.name + suffix)
        if candidate.is_file():
            _copy_source(
                candidate, bundle / "signatures" / ("ledgermind-core" + suffix)
            )
    if not all(
        (bundle / "signatures" / f"ledgermind-core{suffix}").is_file()
        for suffix in (".sig", ".pub")
    ):
        raise SystemExit("signed Core .sig and .pub artifacts are required")
    _copy_source(args.local_source.expanduser(), bundle / "python" / "local")
    for source in args.site_packages:
        source = source.expanduser()
        if not source.is_dir():
            raise SystemExit(f"site-packages directory does not exist: {source}")
        _copy_source(source, bundle / "python" / "site-packages")
    integrations_source = args.integrations_source.expanduser()
    _copy_hermes_plugin(
        _integration_source(integrations_source, "hermes"),
        bundle / "integrations" / "hermes" / "plugin",
        protocol_python=args.protocol_python.expanduser()
        if args.protocol_python
        else None,
    )
    for integration in ("opencode", "openclaw"):
        source = _integration_source(integrations_source, integration)
        _copy_source(source, bundle / "integrations" / integration / "plugin")
    if args.protocol_schemas:
        _copy_source(
            args.protocol_schemas.expanduser(), bundle / "protocol" / "schemas"
        )
    if args.protocol_python:
        _copy_source(args.protocol_python.expanduser(), bundle / "protocol" / "python")
    (bundle / "integrations" / "hermes" / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "hermes",
                "label": "Hermes",
                "capture_schema_version": 1,
                "hooks": [
                    "pre_llm_call",
                    "pre_tool_call",
                    "post_tool_call",
                    "post_llm_call",
                    "on_session_end",
                ],
                "runtime_lease": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (bundle / "integrations" / "hermes" / "adapter.json").write_text(
        json.dumps(
            {
                "id": "hermes",
                "entrypoint": "ledgermind_integrations.adapters.hermes.plugin_entry:register",
                "installation_record": "installation-record.json",
                "runtime": "on-demand-lease",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    installer_python = installer.parent / "python"
    if installer_python.is_dir():
        _copy_source(installer_python, bundle / "python")
    dependency_root = bundle / "python" / "site-packages"
    if not dependency_root.is_dir() or not any(dependency_root.iterdir()):
        raise SystemExit(
            "prebuilt Python site-packages are required for the Local bundle"
        )
    required_integration_runtime = (
        "ledgermind_integrations/adapters/lifecycle/__init__.py",
        "ledgermind_integrations/adapters/lifecycle/bridge.py",
        "ledgermind_integrations/adapters/lifecycle/config.py",
    )
    missing_integration_runtime = [
        relative
        for relative in required_integration_runtime
        if not (dependency_root / relative).is_file()
    ]
    if missing_integration_runtime:
        raise SystemExit(
            "prebuilt Python site-packages are missing the lifecycle integration runtime: "
            + ", ".join(missing_integration_runtime)
        )
    python_runtime = args.python_runtime or (installer.parent / "runtime")
    python_binary = python_runtime / "bin" / "python3.12"
    if not python_binary.is_file():
        raise SystemExit(
            "a bundled CPython 3.12 runtime is required for the Local bundle; "
            "pass --python-runtime"
        )
    _copy_source(python_runtime, bundle / "python" / "runtime")
    local_launcher = bundle / "bin" / "ledgermind-local"
    local_launcher.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\n'
        'runtime="$root/python/runtime/bin/python3.12"\n'
        'if [ ! -x "$runtime" ]; then\n'
        "  printf '%s\\n' 'bundled Python 3.12 runtime is missing' >&2\n"
        "  exit 6\n"
        "fi\n"
        'if [ -d "$root/python/local/src" ]; then\n'
        '  export PYTHONPATH="$root/python/local/src:$root/python/site-packages${PYTHONPATH:+:$PYTHONPATH}"\n'
        "else\n"
        '  export PYTHONPATH="$root/python/local:$root/python/site-packages${PYTHONPATH:+:$PYTHONPATH}"\n'
        "fi\n"
        'exec "$runtime" -m ledgermind_local.cli "$@"\n',
        encoding="utf-8",
    )
    os.chmod(local_launcher, 0o700)
    signing_key = _private_key(args.signing_key.expanduser())
    public_key = _public_bytes(signing_key)
    installer_metadata_path = installer.with_suffix(installer.suffix + ".json")
    if not installer_metadata_path.is_file():
        raise SystemExit(
            "installer metadata is required to verify its embedded release key"
        )
    try:
        installer_metadata = json.loads(
            installer_metadata_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("installer metadata is invalid") from exc
    if (
        not isinstance(installer_metadata, dict)
        or installer_metadata.get("public_key_fingerprint")
        != hashlib.sha256(public_key).hexdigest()
    ):
        raise SystemExit("installer embedded key does not match --signing-key")
    public_key_path = args.public_key.expanduser() if args.public_key else None
    if public_key_path is not None:
        if not public_key_path.is_file():
            raise SystemExit(f"public key artifact does not exist: {public_key_path}")
        _copy_source(public_key_path, bundle / "signatures" / "manifest.pub")
    else:
        (bundle / "signatures" / "manifest.pub").write_bytes(public_key)
        os.chmod(bundle / "signatures" / "manifest.pub", 0o600)
    if public_key_path is not None:
        if _public_key_bytes(public_key_path) != public_key:
            raise SystemExit("--public-key does not match --signing-key")
        os.chmod(bundle / "signatures" / "manifest.pub", 0o600)
    _copy_runtime(
        args.embedding_runtime_cpu,
        bundle / "embedding-runtimes" / "cpu",
        device="cpu",
    )
    _copy_runtime(
        args.embedding_runtime_cuda,
        bundle / "embedding-runtimes" / "cuda",
        device="cuda",
    )
    _copy_runtime(
        args.embedding_runtime_rocm,
        bundle / "embedding-runtimes" / "rocm",
        device="rocm",
    )
    if args.embedding_catalog and args.embedding_catalog.is_file():
        catalog_payload = json.loads(args.embedding_catalog.read_text(encoding="utf-8"))
        entries = (
            catalog_payload
            if isinstance(catalog_payload, list)
            else catalog_payload.get("models", [])
        )
        gpu_entries = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and set(entry.get("devices", [])) & {"cuda", "rocm"}
        ]
        runtime_sources = {
            "cpu": args.embedding_runtime_cpu,
            "cuda": args.embedding_runtime_cuda,
            "rocm": args.embedding_runtime_rocm,
        }
        required_devices = {
            str(device)
            for entry in entries
            if isinstance(entry, dict)
            for device in entry.get("devices", [])
        }
        missing_runtimes = sorted(
            device
            for device in required_devices
            if runtime_sources.get(device) is None
            or not (bundle / "embedding-runtimes" / device).is_dir()
            or not any((bundle / "embedding-runtimes" / device).iterdir())
        )
        if missing_runtimes:
            raise SystemExit(
                "embedding catalog devices require bundled runtimes: "
                + ", ".join(missing_runtimes)
            )
        if gpu_entries and (
            args.hardware_gate_evidence is None
            or not args.hardware_gate_evidence.is_file()
        ):
            raise SystemExit(
                "CUDA/ROCm catalog entries require explicit hardware-gate evidence"
            )
        _copy_source(args.embedding_catalog, bundle / "embedding-catalog.json")
        if args.hardware_gate_evidence and args.hardware_gate_evidence.is_file():
            _copy_source(
                args.hardware_gate_evidence,
                bundle / "embedding-hardware-gate.json",
            )

    artifacts: dict[str, Any] = {}
    for path in sorted(item for item in bundle.rglob("*") if item.is_file()):
        relative = str(path.relative_to(bundle))
        artifacts[relative] = {"size": path.stat().st_size, "sha256": _sha256(path)}
    bundle_manifest = {
        "schema_version": 1,
        "release_version": args.release_version,
        "platform": args.platform,
        "artifacts": artifacts,
        "components": {"core": {}, "local": {}, "integrations": {}, "protocol": {}},
    }
    bundle_manifest_bytes = (
        json.dumps(bundle_manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (bundle / "bundle-manifest.json").write_bytes(bundle_manifest_bytes)
    (bundle / "signatures" / "manifest.sig").write_bytes(
        signing_key.sign(bundle_manifest_bytes)
    )
    os.chmod(bundle / "signatures" / "manifest.sig", 0o600)
    archive = output / f"ledgermind-{args.platform}.tar.zst"
    tar_command = ["tar", "--zstd", "-C", str(output), "-cf", str(archive), "bundle"]
    try:
        subprocess.run(tar_command, check=True)
    except (OSError, subprocess.CalledProcessError):
        # A release gate must not silently call an uncompressed artifact a zstd
        # archive.  Keep the directory for local inspection and fail clearly.
        raise SystemExit("tar --zstd is required to create the platform bundle")
    installer_asset = output / f"ledgermind-installer-{args.platform}"
    shutil.copy2(installer, installer_asset)
    os.chmod(installer_asset, 0o700)
    archive_signature = signing_key.sign(archive.read_bytes())
    installer_signature = signing_key.sign(installer_asset.read_bytes())
    manifest = {
        "schema_version": 1,
        "release_version": args.release_version,
        "published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "public_key_fingerprint": hashlib.sha256(public_key).hexdigest(),
        "platforms": {
            args.platform: {
                "installer": {
                    "url": f"ledgermind-installer-{args.platform}",
                    "size": installer_asset.stat().st_size,
                    "sha256": _sha256(installer_asset),
                    "signature": base64.b64encode(installer_signature).decode("ascii"),
                    "platform": args.platform,
                    "minimum_glibc": "2.31",
                    "component_compatibility": {
                        "release_version": args.release_version
                    },
                },
                "bundle": {
                    "url": f"ledgermind-{args.platform}.tar.zst",
                    "size": archive.stat().st_size,
                    "sha256": _sha256(archive),
                    "signature": base64.b64encode(archive_signature).decode("ascii"),
                    "platform": args.platform,
                    "minimum_glibc": "2.31",
                    "component_compatibility": {
                        "release_version": args.release_version
                    },
                },
            }
        },
        "components": bundle_manifest["components"],
        "embedding_catalog": [],
    }
    if args.embedding_catalog and args.embedding_catalog.is_file():
        catalog = json.loads(args.embedding_catalog.read_text(encoding="utf-8"))
        manifest["embedding_catalog"] = (
            catalog if isinstance(catalog, list) else catalog.get("models", [])
        )
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (output / "install-manifest.json").write_bytes(manifest_bytes)
    (output / "install-manifest.sig").write_bytes(signing_key.sign(manifest_bytes))
    os.chmod(output / "install-manifest.sig", 0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
