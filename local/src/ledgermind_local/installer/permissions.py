"""Private filesystem permissions used by the installer."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import PermissionInstallerError


def ensure_private_dir(path: str | Path) -> Path:
    target = Path(path).expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target, 0o700)
        mode = target.stat().st_mode & 0o777
    except OSError as exc:
        raise PermissionInstallerError(
            f"cannot create private directory: {target}"
        ) from exc
    if mode != 0o700:
        raise PermissionInstallerError(f"directory is not private: {target}")
    return target


def ensure_private_file(path: str | Path) -> Path:
    target = Path(path).expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target.parent, 0o700)
        if not target.exists():
            target.touch(mode=0o600)
        os.chmod(target, 0o600)
        mode = target.stat().st_mode & 0o777
    except OSError as exc:
        raise PermissionInstallerError(f"cannot create private file: {target}") from exc
    if mode != 0o600:
        raise PermissionInstallerError(f"file is not private: {target}")
    return target


def assert_private(path: str | Path, *, directory: bool | None = None) -> None:
    target = Path(path).expanduser()
    try:
        mode = target.stat().st_mode & 0o777
    except OSError as exc:
        raise PermissionInstallerError(f"cannot inspect permissions: {target}") from exc
    expected = 0o700 if (directory is True or target.is_dir()) else 0o600
    if mode != expected:
        raise PermissionInstallerError(
            f"unexpected permissions for {target}: {oct(mode)}, expected {oct(expected)}"
        )


__all__ = ["assert_private", "ensure_private_dir", "ensure_private_file"]
