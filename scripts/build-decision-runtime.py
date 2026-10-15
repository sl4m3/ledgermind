#!/usr/bin/env python3
"""Build a separate, relocatable Kev r10 CPU/BF16 artifact; never edit host Python.

Inputs are a standalone Python distribution and the pinned cached model/base
snapshots plus loader checkout. Dependency installation happens at release build
time only, never on an end-user machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

MODEL_REVISION = "139fdd94f1b6a6ad80cc15e08fcb99cac885a101"
LOADER_REVISION = "3e1cd3bb588a388a06827443380befece23e68c7"
BASE_REVISION = "1001bb4d826a52d1f399e183466143f4da7b741b"
PACKAGES = (
    "torch==2.8.0",
    "transformers==5.17.0",
    "tokenizers==0.23.2",
    "peft==0.21.0",
    "pydantic==2.13.5",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "python-runtime",
        "model",
        "base",
        "loader",
        "output",
        "archive",
        "signing-key",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.archive.exists():
        raise SystemExit("output and archive must not already exist")
    if (
        args.model.resolve().name != MODEL_REVISION
        or args.base.resolve().name != BASE_REVISION
    ):
        raise SystemExit("model/base snapshot revision mismatch")
    revision = subprocess.check_output(
        ["git", "-C", str(args.loader), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != LOADER_REVISION:
        raise SystemExit("loader revision mismatch")
    dirty = subprocess.check_output(
        ["git", "-C", str(args.loader), "status", "--porcelain"], text=True
    )
    if dirty.strip():
        raise SystemExit("loader checkout must be clean")
    if not (args.python_runtime / "bin/python3").is_file():
        raise SystemExit("a standalone Python runtime is required")
    shutil.copytree(args.python_runtime, args.output, symlinks=False)
    python = args.output / "bin/python3"
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--break-system-packages",
            "--index-url",
            "https://download.pytorch.org/whl/cpu",
            PACKAGES[0],
        ],
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--break-system-packages",
            *PACKAGES[1:],
        ],
        check=True,
    )
    for source, target in (
        (args.model, "model"),
        (args.base, "base"),
        (args.loader, "loader"),
    ):
        shutil.copytree(
            source,
            args.output / target,
            symlinks=False,
            ignore=shutil.ignore_patterns(
                ".git", "__pycache__", ".pytest_cache", "runs", ".env", ".env.*"
            ),
        )
    frozen = subprocess.check_output(
        [str(python), "-m", "pip", "freeze", "--all"], text=True
    )
    (args.output / "dependencies.lock").write_text(frozen)
    descriptor = {
        "schema_version": 1,
        "runtime": "kev-4b-r10-cpu",
        "model_revision": MODEL_REVISION,
        "loader_revision": LOADER_REVISION,
        "base_revision": BASE_REVISION,
        "device": "cpu",
        "dtype": "bfloat16",
        "quantization": False,
        "truncation": False,
        "packages": list(PACKAGES),
        "platform": "linux-x86_64",
    }
    (args.output / "decision-runtime.json").write_text(
        json.dumps(descriptor, indent=2) + "\n"
    )
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with args.archive.open("wb") as destination:
        process = subprocess.Popen(
            ["zstd", "-T4", "-3", "-c"], stdin=subprocess.PIPE, stdout=destination
        )
        try:
            with tarfile.open(
                fileobj=process.stdin, mode="w|", dereference=True
            ) as archive:
                for path in sorted(args.output.iterdir()):
                    archive.add(path, arcname=path.name)
        finally:
            if process.stdin:
                process.stdin.close()
        if process.wait() != 0:
            raise SystemExit("runtime compression failed")
    with args.archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    manifest = {
        **descriptor,
        "archive": args.archive.name,
        "size": args.archive.stat().st_size,
        "sha256": digest,
    }
    payload = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    key = Ed25519PrivateKey.from_private_bytes(args.signing_key.read_bytes())
    args.archive.with_name(args.archive.name + ".json").write_bytes(payload)
    args.archive.with_name(args.archive.name + ".sig").write_bytes(key.sign(payload))
    print(
        json.dumps(
            {
                "archive": str(args.archive),
                "sha256": digest,
                "runtime": descriptor["runtime"],
            }
        )
    )


if __name__ == "__main__":
    main()
