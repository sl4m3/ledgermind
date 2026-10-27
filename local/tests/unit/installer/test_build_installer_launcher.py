from __future__ import annotations

import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path


def test_self_contained_launcher_prefers_current_local_source(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    source = tmp_path / "source"
    source.mkdir()
    (source / "ledgermind_local").mkdir()
    runtime = tmp_path / "runtime"
    executable = runtime / "bin" / "python3"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)
    dependencies = tmp_path / "site-packages"
    dependencies.mkdir()
    extra_source = tmp_path / "extra-source"
    extra_package = extra_source / "ledgermind_integrations"
    extra_package.mkdir(parents=True)
    (extra_package / "__init__.py").write_text("CURRENT = True\n", encoding="utf-8")
    output = tmp_path / "ledgermind"

    subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "build-installer.py"),
            "--output",
            str(output),
            "--source",
            str(source),
            "--site-packages",
            str(dependencies),
            "--extra-source",
            str(extra_source),
            "--runtime-root",
            str(runtime),
        ],
        check=True,
    )

    launcher = output.read_bytes().split(b"\n__LEDGERMIND_PAYLOAD_BELOW__\n", 1)[0]
    assert b'PYTHONPATH="$payload_root/python:$payload_root/python/site-packages' in launcher
    archive = output.read_bytes().split(b"\n__LEDGERMIND_PAYLOAD_BELOW__\n", 1)[1]
    with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as payload:
        embedded = payload.extractfile("python/ledgermind_integrations/__init__.py")
        assert embedded is not None
        assert embedded.read() == b"CURRENT = True\n"
