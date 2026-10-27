"""Installation preflight checks."""

from __future__ import annotations

import os
import platform
import shutil
import tempfile
from pathlib import Path

from .errors import PreflightError, UnsupportedPlatformError
from .hardware import detect_devices
from .paths import InstallerPaths


def platform_id() -> str:
    machine = os.uname().machine.lower()
    if machine in {"x86_64", "amd64"}:
        return "linux-x86_64"
    if machine in {"aarch64", "arm64"}:
        return "linux-aarch64"
    raise UnsupportedPlatformError(f"unsupported Linux architecture: {machine}")


def check_preflight(
    paths: InstallerPaths,
    *,
    required_bytes: int = 0,
    require_linux: bool = True,
    minimum_glibc: str | None = None,
    require_bubblewrap: bool = True,
) -> dict[str, object]:
    if require_linux and os.name != "posix":
        raise UnsupportedPlatformError("the first release supports Linux only")
    try:
        current_platform = platform_id()
    except AttributeError as exc:
        raise UnsupportedPlatformError("platform detection is unavailable") from exc
    libc_name, libc_version = platform.libc_ver()
    if minimum_glibc is not None:
        try:
            current_parts = tuple(int(part) for part in libc_version.split("."))
            required_parts = tuple(int(part) for part in minimum_glibc.split("."))
        except ValueError as exc:
            raise PreflightError("glibc version could not be validated") from exc
        if libc_name != "glibc" or current_parts < required_parts:
            raise UnsupportedPlatformError(
                f"glibc {minimum_glibc} or newer is required; found "
                f"{libc_name or 'unknown'} {libc_version or 'unknown'}"
            )
    bubblewrap = shutil.which("bwrap") is not None
    if require_bubblewrap and not bubblewrap:
        raise PreflightError(
            "bubblewrap (bwrap) is required for Core network and filesystem isolation"
        )
    data_dir = paths.data_dir
    parent = data_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not os.access(parent, os.W_OK):
        raise PreflightError(f"installation path is not writable: {parent}")
    usage = shutil.disk_usage(parent)
    if usage.free < required_bytes:
        raise PreflightError("insufficient disk space for installation")
    descriptor, raw_probe = tempfile.mkstemp(
        prefix=".ledgermind-preflight-", dir=parent
    )
    os.close(descriptor)
    probe = Path(raw_probe)
    try:
        probe.unlink()
    except OSError as exc:
        raise PreflightError("cannot write installation staging path") from exc
    return {
        "platform": current_platform,
        "libc": libc_version or "unknown",
        "bubblewrap": bubblewrap,
        "free_bytes": usage.free,
        "devices": [device.as_dict() for device in detect_devices()],
    }


__all__ = ["check_preflight", "platform_id"]
