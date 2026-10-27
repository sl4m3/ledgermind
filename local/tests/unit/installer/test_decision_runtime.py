from __future__ import annotations

import io
import json
import subprocess
import tarfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ledgermind_local.installer.decision_runtime import (
    IDENTITY,
    install_decision_runtime,
)
from ledgermind_local.installer.verify import sha256_file


def artifact(tmp_path, *, unsafe=False):
    tar_path = tmp_path / "runtime.tar"
    entries = {"decision-runtime.json": json.dumps(IDENTITY).encode()}
    for name in (
        "bin/python3",
        "model/head.pt",
        "model/adapter_config.json",
        "model/adapter_model.safetensors",
        "base/config.json",
        "loader/kev/api.py",
        "dependencies.lock",
    ):
        entries[name] = b"test"
    if unsafe:
        entries["../outside"] = b"forbidden"
    with tarfile.open(tar_path, "w") as archive:
        for name, payload in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    archive_path = tmp_path / "runtime.tar.zst"
    subprocess.run(["zstd", "-q", str(tar_path), "-o", str(archive_path)], check=True)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                **IDENTITY,
                "archive": archive_path.name,
                "size": archive_path.stat().st_size,
                "sha256": sha256_file(archive_path),
            }
        )
    )
    key = Ed25519PrivateKey.generate()
    signature = tmp_path / "manifest.sig"
    signature.write_bytes(key.sign(manifest.read_bytes()))
    return dict(
        archive=archive_path,
        manifest=manifest,
        signature=signature,
        trusted_public_key=key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        ),
        destination=tmp_path / "installed",
    )


def test_signed_runtime_installs_atomically_without_host_pip(tmp_path):
    args = artifact(tmp_path)
    root = install_decision_runtime(**args)
    assert (root / "installed-manifest.sig").is_file()
    with pytest.raises(ValueError, match="already exists"):
        install_decision_runtime(**args)


def test_runtime_rejects_path_traversal_and_cleans_own_staging(tmp_path):
    args = artifact(tmp_path, unsafe=True)
    with pytest.raises(ValueError, match="unsafe"):
        install_decision_runtime(**args)
    assert not args["destination"].exists()
    assert not (tmp_path / "outside").exists()
    assert not list(tmp_path.glob(".decision-install-*"))


def test_runtime_rejects_modified_signed_manifest(tmp_path):
    args = artifact(tmp_path)
    args["manifest"].write_text("{}")
    with pytest.raises(Exception):
        install_decision_runtime(**args)
    assert not args["destination"].exists()
