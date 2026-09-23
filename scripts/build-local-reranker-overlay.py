#!/usr/bin/env python3
"""Build a signed local-only release overlay without touching the source release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _digest(path: Path) -> str:
    hash_ = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hash_.update(chunk)
    return hash_.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-release", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--local-package", type=Path, required=True)
    parser.add_argument("--inference-package", type=Path, required=True)
    parser.add_argument("--protocol-package", type=Path, required=True)
    parser.add_argument("--integrations-package", type=Path, required=True)
    parser.add_argument("--core-binary", type=Path)
    parser.add_argument("--core-signing-key", type=Path)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    source = args.source_release.resolve(strict=True)
    destination = args.destination.expanduser().absolute()
    if destination.exists():
        raise SystemExit(f"destination already exists: {destination}")
    key = Ed25519PrivateKey.from_private_bytes(args.signing_key.read_bytes())
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    if public != (source / "signatures" / "manifest.pub").read_bytes():
        raise SystemExit("signing key does not match installed release")
    shutil.copytree(source, destination, symlinks=True)
    for source_path, target in (
        (args.local_package, destination / "python" / "local" / "ledgermind_local"),
        (args.inference_package, destination / "python" / "site-packages" / "ledgermind_inference"),
        (args.protocol_package, destination / "python" / "site-packages" / "ledgermind_protocol"),
        (args.integrations_package, destination / "python" / "site-packages" / "ledgermind_integrations"),
    ):
        shutil.copytree(
            source_path.resolve(strict=True), target, dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    if bool(args.core_binary) != bool(args.core_signing_key):
        raise SystemExit("core binary and signing key must be supplied together")
    if args.core_binary:
        core_key = Ed25519PrivateKey.from_private_bytes(
            args.core_signing_key.read_bytes()
        )
        core_public = core_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        if core_public != (source / "signatures" / "ledgermind-core.pub").read_bytes():
            raise SystemExit("Core signing key does not match installed release")
        core_path = destination / "bin" / "ledgermind-core"
        shutil.copy2(args.core_binary.resolve(strict=True), core_path)
        (destination / "signatures" / "ledgermind-core.sig").write_bytes(
            core_key.sign(core_path.read_bytes())
        )
    artifacts = {}
    for path in sorted(destination.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(destination).as_posix()
        if relative in {"bundle-manifest.json", "signatures/manifest.sig"}:
            continue
        artifacts[relative] = {"size": path.stat().st_size, "sha256": _digest(path)}
    manifest = json.loads((source / "bundle-manifest.json").read_text())
    manifest["release_version"] = args.version
    manifest["artifacts"] = artifacts
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (destination / "bundle-manifest.json").write_bytes(manifest_bytes)
    (destination / "signatures" / "manifest.sig").write_bytes(key.sign(manifest_bytes))
    key.public_key().verify(
        (destination / "signatures" / "manifest.sig").read_bytes(), manifest_bytes
    )
    print(json.dumps({
        "release": str(destination),
        "version": args.version,
        "artifacts": len(artifacts),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
