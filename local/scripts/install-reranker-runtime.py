#!/usr/bin/env python3
"""Verify and install a separately downloaded Qwen runtime archive offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--trusted-public-key", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    payload = args.manifest.read_bytes()
    Ed25519PublicKey.from_public_bytes(args.trusted_public_key.read_bytes()).verify(
        args.signature.read_bytes(), payload
    )
    manifest = json.loads(payload)
    if (manifest.get("schema_version") != 1
            or manifest.get("runtime") != "qwen3-reranker-0.6b-cpu"
            or manifest.get("platform") != "linux-x86_64"
            or manifest.get("archive") != archive.name
            or manifest.get("size") != archive.stat().st_size
            or manifest.get("sha256") != _digest(archive)):
        raise SystemExit("reranker runtime manifest or checksum mismatch")
    destination = args.destination.expanduser().absolute()
    if destination.exists():
        raise SystemExit(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".reranker-install-", dir=destination.parent))
    try:
        process = subprocess.Popen(
            ["zstd", "-dc", "--", str(archive)], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdout is not None
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as stream:
                for member in stream:
                    relative = PurePosixPath(member.name)
                    if (relative.is_absolute() or ".." in relative.parts
                            or not relative.parts
                            or relative.parts[0] not in {"site-packages", "model"}
                            or not (member.isfile() or member.isdir())):
                        raise ValueError(f"unsafe runtime member: {member.name}")
                    target = staging.joinpath(*relative.parts)
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        source = stream.extractfile(member)
                        assert source is not None
                        with source, target.open("wb") as output:
                            shutil.copyfileobj(source, output)
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdout.close()
        if process.wait(timeout=30) != 0:
            raise RuntimeError("reranker runtime decompression failed")
        revision = manifest["model_revision"]
        if not (staging / "model" / "snapshots" / revision / "model.safetensors").is_file():
            raise ValueError("reranker model snapshot is incomplete")
        if not (staging / "site-packages" / "torch" / "__init__.py").is_file():
            raise ValueError("reranker inference runtime is incomplete")
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(json.dumps({"status": "installed", "runtime_path": str(destination)}, sort_keys=True))


if __name__ == "__main__":
    main()
