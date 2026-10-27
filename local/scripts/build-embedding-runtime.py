#!/usr/bin/env python3
"""Build the signed, relocatable CPU embedding runtime used by the installer.

The resulting directory is an input to ``build-platform-bundle.py``. Dependency
resolution happens only while producing a release; user installations copy the
already-built runtime and never invoke pip.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

TORCH_VERSION = "2.11.0"
TRANSFORMERS_VERSION = "5.5.0"
SENTENCE_TRANSFORMERS_VERSION = "5.4.1"
PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="build LedgerMind's relocatable CPU embedding runtime"
    )
    parser.add_argument("--python-runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _run(*command: str) -> str:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SystemExit(f"runtime build command failed: {detail}")
    return completed.stdout.strip()


def main() -> int:
    args = _parser().parse_args()
    source = args.python_runtime.expanduser().resolve()
    output = args.output.expanduser().resolve()
    source_python = source / "bin" / "python3"
    if not source_python.is_file():
        raise SystemExit("--python-runtime must contain bin/python3")
    if output.exists():
        raise SystemExit(f"output already exists: {output}")

    shutil.copytree(source, output, symlinks=True)
    runtime_python = output / "bin" / "python3"
    _run(
        str(runtime_python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--break-system-packages",
        "--index-url",
        PYTORCH_CPU_INDEX,
        f"torch=={TORCH_VERSION}",
    )
    _run(
        str(runtime_python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--break-system-packages",
        f"transformers=={TRANSFORMERS_VERSION}",
        f"sentence-transformers=={SENTENCE_TRANSFORMERS_VERSION}",
    )
    smoke = json.loads(
        _run(
            str(runtime_python),
            "-c",
            "import json, sentence_transformers, torch, transformers; "
            "print(json.dumps({'torch': torch.__version__, "
            "'transformers': transformers.__version__, "
            "'sentence_transformers': sentence_transformers.__version__, "
            "'cuda_available': torch.cuda.is_available()}))",
        ).splitlines()[-1]
    )
    if smoke["transformers"] != TRANSFORMERS_VERSION:
        raise SystemExit("installed transformers version does not match the lock")
    if smoke["sentence_transformers"] != SENTENCE_TRANSFORMERS_VERSION:
        raise SystemExit(
            "installed sentence-transformers version does not match the lock"
        )
    if smoke["cuda_available"]:
        raise SystemExit("CPU runtime unexpectedly exposes a CUDA device")

    metadata = {
        "schema_version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "device": "cpu",
        "packages": smoke,
        "pytorch_index": PYTORCH_CPU_INDEX,
        "pip_freeze": _run(str(runtime_python), "-m", "pip", "freeze").splitlines(),
    }
    (output / "runtime-build.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
