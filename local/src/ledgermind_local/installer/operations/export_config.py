"""Export configuration with secrets excluded unless explicitly requested."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..config_writer import load_installer_config, select_secret_backend
from ..paths import InstallerPaths
from ..secret_refs import EMBEDDING_SECRET_REF, GENERATION_SECRET_REF


def export_config(
    *, paths: InstallerPaths, out: str | Path, include_secrets: bool = False
) -> dict[str, Any]:
    config = load_installer_config(paths.config_file)
    payload: dict[str, Any] = config.model_dump(mode="json", exclude_none=True)
    if include_secrets:
        backend = select_secret_backend(paths)
        secrets: dict[str, str] = {}
        for key in (GENERATION_SECRET_REF, EMBEDDING_SECRET_REF):
            value = backend.get(key)
            if value is not None:
                secrets[key] = value
        payload["secrets"] = secrets
    target = Path(out).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
        os.chmod(target, 0o600)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"status": "passed", "out": str(target), "include_secrets": include_secrets}


__all__ = ["export_config"]
