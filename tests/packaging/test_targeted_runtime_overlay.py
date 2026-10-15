"""A GPU endpoint patch must leave Core and all other Python packages alone."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/build-local-reranker-overlay.py"


def fixture_command(tmp_path, relative="installer/embeddings/service.py"):
    source = tmp_path / "source"
    local = source / "python/local/ledgermind_local"
    files = {
        "bin/ledgermind-core": b"unchanged-core",
        "python/local/ledgermind_local/installer/embeddings/service.py": b"old endpoint\n",
        "python/local/ledgermind_local/unchanged.py": b"unchanged local code\n",
        "python/site-packages/ledgermind_inference/module.py": b"unchanged inference\n",
        "python/site-packages/ledgermind_protocol/module.py": b"unchanged protocol\n",
        "python/site-packages/ledgermind_integrations/module.py": b"unchanged integrations\n",
    }
    for name, content in files.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    key = Ed25519PrivateKey.generate()
    key_path = tmp_path / "test.key"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    (source / "signatures").mkdir()
    (source / "signatures/manifest.pub").write_bytes(public)
    (source / "bundle-manifest.json").write_text(
        json.dumps({"release_version": "original"})
    )
    patch = tmp_path / "endpoint.py"
    patch.write_bytes(b"updated endpoint only\n")
    destination = tmp_path / "new"
    command = [
        sys.executable,
        str(SCRIPT),
        "--source-release",
        str(source),
        "--destination",
        str(destination),
        "--local-package",
        str(local),
    ]
    for package in ("inference", "protocol", "integrations"):
        command += [
            f"--{package}-package",
            str(source / f"python/site-packages/ledgermind_{package}"),
        ]
    command += [
        "--local-file-overlay",
        relative,
        str(patch),
        "--signing-key",
        str(key_path),
        "--version",
        "gpu-local-test",
    ]
    return command, source, destination, files, key


def test_signed_targeted_patch_does_not_upgrade_other_modules(tmp_path):
    command, source, destination, files, key = fixture_command(tmp_path)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    changed = "python/local/ledgermind_local/installer/embeddings/service.py"
    for name, content in files.items():
        assert (source / name).read_bytes() == content
        assert (destination / name).read_bytes() == (
            b"updated endpoint only\n" if name == changed else content
        )
    manifest = (destination / "bundle-manifest.json").read_bytes()
    key.public_key().verify(
        (destination / "signatures/manifest.sig").read_bytes(), manifest
    )
    for name, metadata in json.loads(manifest)["artifacts"].items():
        content = (destination / name).read_bytes()
        assert metadata["sha256"] == hashlib.sha256(content).hexdigest()
        assert metadata["size"] == len(content)


def test_updated_installer_is_included_in_signed_manifest(tmp_path):
    command, source, destination, files, key = fixture_command(tmp_path)
    launcher = tmp_path / "updated-installer"
    launcher.write_bytes(b"#!/bin/sh\n# updated encoder migration\n")
    launcher.chmod(0o700)
    command.extend(["--installer-launcher", str(launcher)])
    subprocess.run(command, capture_output=True, text=True, check=True)
    assert (destination / "bin/ledgermind").read_bytes() == launcher.read_bytes()
    manifest = (destination / "bundle-manifest.json").read_bytes()
    key.public_key().verify((destination / "signatures/manifest.sig").read_bytes(), manifest)
    metadata = json.loads(manifest)["artifacts"]["bin/ledgermind"]
    assert metadata["sha256"] == hashlib.sha256(launcher.read_bytes()).hexdigest()
    assert metadata["size"] == launcher.stat().st_size
    for name, content in files.items():
        assert (source / name).read_bytes() == content


def test_runtime_generated_bytecode_is_not_a_signed_artifact(tmp_path):
    command, source, destination, files, key = fixture_command(tmp_path)
    cache = source / "python/site-packages/ledgermind_integrations/__pycache__/module.cpython-312.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"obsolete bytecode")
    subprocess.run(command, capture_output=True, check=True)
    assert not (destination / cache.relative_to(source)).exists()
    manifest_bytes = (destination / "bundle-manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert not any(path.endswith((".pyc", ".pyo")) for path in manifest["artifacts"])
    # Runtime-generated cache may change without invalidating any shipped code.
    generated = destination / cache.relative_to(source)
    generated.parent.mkdir()
    generated.write_bytes(b"new runtime bytecode")
    key.public_key().verify((destination / "signatures/manifest.sig").read_bytes(), manifest_bytes)
    for relative, record in manifest["artifacts"].items():
        assert hashlib.sha256((destination / relative).read_bytes()).hexdigest() == record["sha256"]


@pytest.mark.parametrize("relative", ["../outside.py", "/outside.py"])
def test_file_overlay_cannot_escape_local_package(tmp_path, relative):
    command, _, destination, _, _ = fixture_command(tmp_path, relative)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode != 0
    assert "invalid Local file overlay" in completed.stderr
    assert not destination.exists()


def test_addition_preserves_existing_modules(tmp_path):
    command, source, destination, files, _ = fixture_command(
        tmp_path, "core_gateway/queued_context.py"
    )
    command[command.index("--local-file-overlay")] = "--local-file-addition"
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert (
        destination / "python/local/ledgermind_local/core_gateway/queued_context.py"
    ).read_bytes() == b"updated endpoint only\n"
    for name, content in files.items():
        assert (source / name).read_bytes() == content
        assert (destination / name).read_bytes() == content


def test_addition_cannot_overwrite_existing_module(tmp_path):
    command, _, destination, _, _ = fixture_command(tmp_path)
    command[command.index("--local-file-overlay")] = "--local-file-addition"
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode != 0
    assert "must not overwrite" in completed.stderr
    assert not destination.exists()


@pytest.mark.parametrize("relative", ["../outside.py", "/outside.py"])
def test_addition_cannot_escape_local_package(tmp_path, relative):
    command, _, destination, _, _ = fixture_command(tmp_path, relative)
    command[command.index("--local-file-overlay")] = "--local-file-addition"
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode != 0
    assert "invalid Local file overlay" in completed.stderr
    assert not destination.exists()
