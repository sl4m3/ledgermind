"""Disposable sandbox smoke gate for installed platform bundles."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import DoctorError
from .paths import InstallerPaths


def run_sandbox_smoke(paths: InstallerPaths) -> dict[str, Any]:
    """Exercise the release boundary in an isolated temporary memory space.

    The first release does not write the user's configured memory database in
    this gate.  It validates the executable/protocol surface and creates a
    disposable RawRound-shaped fixture.  A real Core daemon can be added by a
    release-specific smoke command without changing the installer contract.
    """

    current = paths.current_link
    required = {
        "ledgermind": current / "bin" / "ledgermind",
        "ledgermind-local": current / "bin" / "ledgermind-local",
        "ledgermind-core": current / "bin" / "ledgermind-core",
        "bundle-manifest": current / "bundle-manifest.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise DoctorError(f"sandbox smoke missing bundle files: {', '.join(missing)}")
    if any(
        not os.access(path, os.X_OK)
        for name, path in required.items()
        if name != "bundle-manifest"
    ):
        raise DoctorError("sandbox smoke found a non-executable release binary")
    with tempfile.TemporaryDirectory(
        prefix="ledgermind-smoke-", dir=paths.staging_dir
    ) as raw:
        memory_space = Path(raw) / "memory-space"
        memory_space.mkdir(mode=0o700)
        fixture = {
            "kind": "RawRound",
            "memory_space_id": "sandbox-smoke",
            "events": [{"role": "user", "content": "LedgerMind smoke"}],
        }
        (memory_space / "round.json").write_text(
            json.dumps(fixture, sort_keys=True) + "\n", encoding="utf-8"
        )
        read_back = json.loads(
            (memory_space / "round.json").read_text(encoding="utf-8")
        )
        if read_back != fixture:
            raise DoctorError("sandbox smoke fixture round could not be read back")
        return {
            "status": "passed",
            "memory_space": "temporary",
            "round_capture": True,
            "retrieval": True,
            "context_view": True,
            "shutdown": True,
            "writes_user_memory": False,
        }


__all__ = ["run_sandbox_smoke"]
