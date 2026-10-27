#!/usr/bin/env python3
"""Package a verified local overlay for the normal offline update path."""

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from ledgermind_local.installer.verify import sha256_file, verify_bundle_tree


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = Ed25519PrivateKey.from_private_bytes(args.signing_key.read_bytes())
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    verify_bundle_tree(args.bundle, public_key=public)
    args.output.mkdir(parents=True, exist_ok=False)
    archive = args.output / "ledgermind-linux-x86_64.tar.zst"
    subprocess.run(
        [
            "tar",
            "--zstd",
            "-C",
            str(args.bundle.parent.resolve()),
            "-cf",
            str(archive.resolve()),
            args.bundle.name,
        ],
        check=True,
    )
    signature = key.sign(archive.read_bytes())
    record = {
        "url": archive.name,
        "size": archive.stat().st_size,
        "sha256": sha256_file(archive),
        "signature": base64.b64encode(signature).decode(),
        "platform": "linux-x86_64",
        "minimum_glibc": "2.31",
    }
    bundle = json.loads((args.bundle / "bundle-manifest.json").read_text())
    catalog = json.loads((args.bundle / "embedding-catalog.json").read_text())
    installer = args.output / "ledgermind-installer-linux-x86_64"
    shutil.copy2(args.bundle / "bin/ledgermind", installer)
    installer_record = {
        **record,
        "url": installer.name,
        "size": installer.stat().st_size,
        "sha256": sha256_file(installer),
        "signature": base64.b64encode(key.sign(installer.read_bytes())).decode(),
    }
    manifest = {
        "schema_version": 1,
        "release_version": bundle["release_version"],
        "published_at": datetime.now(timezone.utc).isoformat(),
        "public_key_fingerprint": hashlib.sha256(public).hexdigest(),
        "platforms": {
            "linux-x86_64": {"installer": installer_record, "bundle": record}
        },
        "embedding_catalog": catalog["models"],
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (args.output / "install-manifest.json").write_bytes(payload)
    (args.output / "install-manifest.sig").write_bytes(key.sign(payload))
    print(
        json.dumps(
            {
                "archive": str(archive),
                "sha256": record["sha256"],
                "bytes": record["size"],
            }
        )
    )


if __name__ == "__main__":
    main()
