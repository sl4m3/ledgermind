#!/usr/bin/env python3
"""Assemble a test-signed LedgerMind release inside Docker from workspace sources + v5.0.0 Core."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _overlay(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=lambda _path, names: {
            n for n in names if n == "__pycache__" or n.endswith((".pyc", ".pyo"))
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extra-ca-cert", type=Path)
    args = parser.parse_args()

    out = args.output.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    subprocess.run(
        ["tar", "--zstd", "-xf", str(args.artifacts / "ledgermind-linux-x86_64.tar.zst"), "-C", str(out)],
        check=True,
    )
    bundle = out / "bundle"
    if not bundle.is_dir():
        raise SystemExit("expected extracted bundle/ directory")

    # Remove old manifest/signature before regenerating
    (bundle / "bundle-manifest.json").unlink(missing_ok=True)
    (bundle / "signatures" / "manifest.sig").unlink(missing_ok=True)

    # Overlay workspace Python sources while keeping v5.0.0 ledgermind-core + signatures intact
    _overlay(
        args.workspace / "local" / "src" / "ledgermind_local",
        bundle / "python" / "local" / "ledgermind_local",
    )
    _overlay(
        args.workspace / "integrations" / "src" / "ledgermind_integrations",
        bundle / "python" / "site-packages" / "ledgermind_integrations",
    )
    _overlay(
        args.workspace / "protocol" / "python" / "src" / "ledgermind_protocol",
        bundle / "python" / "site-packages" / "ledgermind_protocol",
    )
    _overlay(
        args.workspace / "protocol" / "python" / "src" / "ledgermind_protocol",
        bundle / "protocol" / "python" / "ledgermind_protocol",
    )
    hermes_vendor = bundle / "integrations" / "hermes" / "plugin" / "_vendor"
    if hermes_vendor.is_dir():
        _overlay(
            args.workspace / "integrations" / "src" / "ledgermind_integrations",
            hermes_vendor / "ledgermind_integrations",
        )
        _overlay(
            args.workspace / "protocol" / "python" / "src" / "ledgermind_protocol",
            hermes_vendor / "ledgermind_protocol",
        )

    if args.extra_ca_cert is not None and args.extra_ca_cert.is_file():
        cert_pem = args.extra_ca_cert.read_text(encoding="utf-8")
        cacert = bundle / "python" / "site-packages" / "certifi" / "cacert.pem"
        if cacert.is_file():
            cacert.write_text(
                cacert.read_text(encoding="utf-8") + "\n" + cert_pem,
                encoding="utf-8",
            )

    # Ephemeral Ed25519 release signing keypair (test-only)
    signing_key = Ed25519PrivateKey.generate()
    public_bytes = signing_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_bytes = signing_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    (out / "release.priv").write_bytes(priv_bytes)
    (out / "release.pub").write_bytes(public_bytes)
    (out / "public_key.b64").write_text(
        base64.b64encode(public_bytes).decode("ascii") + "\n", encoding="utf-8"
    )
    (bundle / "signatures" / "manifest.pub").write_bytes(public_bytes)
    os.chmod(bundle / "signatures" / "manifest.pub", 0o600)

    # Rebuild the self-extracting installer binary with workspace sources + ephemeral public key
    installer_asset = out / "ledgermind-installer-linux-x86_64"
    subprocess.run(
        [
            sys.executable,
            str(args.workspace / "local" / "scripts" / "build-installer.py"),
            "--output",
            str(installer_asset),
            "--source",
            str(args.workspace / "local" / "src"),
            "--extra-source",
            str(args.workspace / "integrations" / "src"),
            "--extra-source",
            str(args.workspace / "protocol" / "python" / "src"),
            "--site-packages",
            str(bundle / "python" / "site-packages"),
            "--runtime-root",
            str(bundle / "python" / "runtime"),
            "--runtime-executable",
            "bin/python3.12",
            "--public-key",
            str(out / "release.pub"),
        ],
        check=True,
    )
    shutil.copy2(installer_asset, bundle / "bin" / "ledgermind")
    os.chmod(bundle / "bin" / "ledgermind", 0o700)
    os.chmod(installer_asset, 0o755)

    artifacts_map: dict[str, Any] = {}
    for item in sorted(bundle.rglob("*")):
        if item.is_file():
            rel = str(item.relative_to(bundle))
            artifacts_map[rel] = {"size": item.stat().st_size, "sha256": _sha256(item)}

    bundle_manifest = {
        "schema_version": 1,
        "release_version": "5.0.0-e2e",
        "platform": "linux-x86_64",
        "artifacts": artifacts_map,
        "components": {"core": {}, "local": {}, "integrations": {}, "protocol": {}},
    }
    bm_bytes = (json.dumps(bundle_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (bundle / "bundle-manifest.json").write_bytes(bm_bytes)
    (bundle / "signatures" / "manifest.sig").write_bytes(signing_key.sign(bm_bytes))
    os.chmod(bundle / "signatures" / "manifest.sig", 0o600)

    archive = out / "ledgermind-linux-x86_64.tar.zst"
    subprocess.run(
        ["tar", "--zstd", "-C", str(out), "-cf", str(archive), "bundle"],
        check=True,
    )

    upstream_manifest = json.loads(
        (args.artifacts / "install-manifest.json").read_text(encoding="utf-8")
    )
    archive_sig = signing_key.sign(archive.read_bytes())
    installer_sig = signing_key.sign(installer_asset.read_bytes())
    install_manifest = {
        "schema_version": 1,
        "release_version": "5.0.0-e2e",
        "published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "public_key_fingerprint": hashlib.sha256(public_bytes).hexdigest(),
        "platforms": {
            "linux-x86_64": {
                "installer": {
                    "url": "ledgermind-installer-linux-x86_64",
                    "size": installer_asset.stat().st_size,
                    "sha256": _sha256(installer_asset),
                    "signature": base64.b64encode(installer_sig).decode("ascii"),
                    "platform": "linux-x86_64",
                    "minimum_glibc": "2.31",
                    "component_compatibility": {"release_version": "5.0.0-e2e"},
                },
                "bundle": {
                    "url": "ledgermind-linux-x86_64.tar.zst",
                    "size": archive.stat().st_size,
                    "sha256": _sha256(archive),
                    "signature": base64.b64encode(archive_sig).decode("ascii"),
                    "platform": "linux-x86_64",
                    "minimum_glibc": "2.31",
                    "component_compatibility": {"release_version": "5.0.0-e2e"},
                },
            }
        },
        "components": bundle_manifest["components"],
        "embedding_catalog": upstream_manifest.get("embedding_catalog", []),
    }
    im_bytes = (
        json.dumps(install_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (out / "install-manifest.json").write_bytes(im_bytes)
    (out / "install-manifest.sig").write_bytes(signing_key.sign(im_bytes))
    shutil.copy2(args.workspace / "local" / "scripts" / "install.sh", out / "install.sh")
    os.chmod(out / "install.sh", 0o755)
    print(f"Built test release in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
