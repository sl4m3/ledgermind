from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from ledgermind_local.installer.embeddings.model_download import download_model
from ledgermind_local.installer.embeddings.verification import (
    verify_local_runtime_inference,
    verify_model_files,
)
from ledgermind_local.installer.errors import ConfigurationError
from ledgermind_local.installer.paths import InstallerPaths


def test_signed_model_download_supports_sentence_transformer_subdirectories(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(b"{}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    entry = {
        "id": "nemotron",
        "files": [
            {
                "name": "1_Pooling/config.json",
                "url": source.as_uri(),
                "size": 2,
                "sha256": digest,
            }
        ],
    }

    model_dir = download_model(entry, InstallerPaths(home_override=tmp_path / "home"))

    assert (model_dir / "1_Pooling" / "config.json").read_bytes() == b"{}"
    assert verify_model_files(model_dir, entry)["files_checked"] == 1


def test_signed_model_download_rejects_catalog_path_traversal(tmp_path: Path) -> None:
    entry = {
        "id": "nemotron",
        "files": [{"name": "../escape", "url": "https://example.invalid/file"}],
    }

    with pytest.raises(ConfigurationError, match="path is invalid"):
        download_model(entry, InstallerPaths(home_override=tmp_path / "home"))


def test_local_runtime_smoke_uses_device_python_and_both_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_python = tmp_path / "runtime" / "bin" / "python3"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text("#!/bin/sh\n", encoding="utf-8")
    model = tmp_path / "model"
    model.mkdir()
    captured: dict[str, object] = {}

    def fake_run(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command, 0, stdout='{"status":"passed","dimensions":2048}\n', stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = verify_local_runtime_inference(
        runtime_path=tmp_path / "runtime",
        model_path=model,
        device="cpu",
        dimensions=2048,
    )

    assert result["status"] == "passed"
    command = captured["command"]
    assert isinstance(command, tuple)
    assert command[0] == str(runtime_python)
    assert 'role="query"' in command[2]
    assert 'role="passage"' in command[2]
