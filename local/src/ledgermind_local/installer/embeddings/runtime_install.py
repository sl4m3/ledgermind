"""Install a verified runtime from the platform bundle, never from PyPI."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..errors import ConfigurationError
from ..paths import InstallerPaths
from ..permissions import ensure_private_dir
from ..verify import sha256_file


def install_runtime(
    entry: dict[str, Any],
    *,
    device: str,
    bundle_root: str | Path,
    paths: InstallerPaths,
) -> Path:
    runtime_id = str(entry.get("runtime_id", "")).strip()
    if not runtime_id:
        raise ConfigurationError("embedding runtime id is missing")
    devices = entry.get("devices", [])
    if device not in devices:
        raise ConfigurationError(f"embedding runtime is not approved for {device}")
    source = Path(bundle_root) / "embedding-runtimes" / device
    if not source.is_dir():
        raise ConfigurationError(
            f"signed embedding runtime is missing from bundle: {source}"
        )
    destination = paths.data_dir / "embedding-runtimes" / runtime_id / device
    if destination.exists():
        shutil.rmtree(destination)
    ensure_private_dir(destination.parent)
    shutil.copytree(source, destination)
    for name, expected in dict(entry.get("runtime_sha256", {})).items():
        relative = Path(str(name).replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts or relative == Path("."):
            raise ConfigurationError("embedding runtime contains an unsafe file path")
        file_path = destination / relative
        if not file_path.is_file() or sha256_file(file_path) != str(expected).lower():
            raise ConfigurationError(f"embedding runtime checksum mismatch: {name}")
    runtime_python = destination / "bin" / "python3"
    if not runtime_python.is_file():
        raise ConfigurationError("embedding runtime has no bin/python3 executable")
    runtime_python.chmod(0o700)
    return destination


__all__ = ["install_runtime"]
