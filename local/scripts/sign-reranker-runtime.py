#!/usr/bin/env python3
"""Attach a signed, verifiable manifest to a separately downloadable runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    key = Ed25519PrivateKey.from_private_bytes(args.signing_key.read_bytes())
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {
        "schema_version": 1,
        "runtime": "qwen3-reranker-0.6b-cpu",
        "model_revision": "e61197ed45024b0ed8a2d74b80b4d909f1255473",
        "platform": "linux-x86_64",
        "archive": archive.name,
        "sha256": digest,
        "size": archive.stat().st_size,
    }
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    archive.with_name(archive.name + ".json").write_bytes(payload)
    archive.with_name(archive.name + ".sig").write_bytes(key.sign(payload))
    archive.with_name(archive.name + ".pub").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
