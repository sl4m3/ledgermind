"""Offline installation of the separately signed Kev runtime artifact."""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from .verify import sha256_file, verify_ed25519

IDENTITY = {
    "schema_version": 1,
    "runtime": "kev-4b-r10-cpu",
    "platform": "linux-x86_64",
    "model_revision": "139fdd94f1b6a6ad80cc15e08fcb99cac885a101",
    "loader_revision": "3e1cd3bb588a388a06827443380befece23e68c7",
    "base_revision": "1001bb4d826a52d1f399e183466143f4da7b741b",
    "device": "cpu",
    "dtype": "bfloat16",
    "quantization": False,
    "truncation": False,
}


def install_decision_runtime(
    *,
    archive: Path,
    manifest: Path,
    signature: Path,
    trusted_public_key: bytes,
    destination: Path,
) -> Path:
    # The key must come from the user's existing release trust configuration,
    # not from a .pub file shipped next to an untrusted download.
    payload = manifest.read_bytes()
    verify_ed25519(payload, signature.read_bytes(), trusted_public_key)
    metadata = json.loads(payload)
    if any(metadata.get(key) != value for key, value in IDENTITY.items()):
        raise ValueError("decision runtime identity mismatch")
    if (
        metadata.get("archive") != archive.name
        or metadata.get("size") != archive.stat().st_size
        or metadata.get("sha256") != sha256_file(archive)
    ):
        raise ValueError("decision runtime archive checksum mismatch")
    destination = destination.expanduser().absolute()
    if destination.exists():
        raise ValueError("decision runtime destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(prefix=".decision-install-", dir=destination.parent)
    )
    try:
        process = subprocess.Popen(
            ["zstd", "-dc", "--", str(archive.resolve())],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        assert process.stdout is not None
        total = 0
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as stream:
                for member in stream:
                    relative = PurePosixPath(member.name)
                    if (
                        relative.is_absolute()
                        or ".." in relative.parts
                        or not relative.parts
                        or not (member.isfile() or member.isdir())
                    ):
                        raise ValueError("unsafe decision runtime member")
                    total += member.size
                    if total > 128 * 1024**3:
                        raise ValueError("decision runtime exceeds unpacked size limit")
                    target = staging.joinpath(*relative.parts)
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True, mode=0o700)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        source = stream.extractfile(member)
                        assert source is not None
                        with source, target.open("wb") as output:
                            shutil.copyfileobj(source, output)
                        target.chmod(0o700 if member.mode & 0o111 else 0o600)
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdout.close()
        if process.wait(timeout=30) != 0:
            raise ValueError("decision runtime decompression failed")
        descriptor = json.loads((staging / "decision-runtime.json").read_text())
        if any(descriptor.get(key) != value for key, value in IDENTITY.items()):
            raise ValueError("decision runtime descriptor mismatch")
        for required in (
            "bin/python3",
            "model/head.pt",
            "model/adapter_config.json",
            "model/adapter_model.safetensors",
            "base/config.json",
            "loader/kev/api.py",
            "dependencies.lock",
        ):
            if not (staging / required).is_file():
                raise ValueError(f"incomplete decision runtime: {required}")
        (staging / "installed-manifest.json").write_bytes(payload)
        (staging / "installed-manifest.sig").write_bytes(signature.read_bytes())
        staging.rename(destination)
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging)
