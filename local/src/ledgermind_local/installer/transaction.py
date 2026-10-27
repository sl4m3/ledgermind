"""Transactional release staging, commit, and rollback."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .errors import TransactionError
from .paths import InstallerPaths
from .permissions import ensure_private_dir


@dataclass(slots=True)
class TransactionSnapshot:
    release_version: str
    release_dir: Path
    previous_target: str | None
    current_switched: bool = False


@dataclass(slots=True)
class FileBackup:
    path: Path
    existed: bool
    content: bytes = b""
    mode: int = 0o600


def _atomic_symlink(target: Path, link: Path) -> None:
    temporary = link.with_name(f".{link.name}.{uuid4().hex}.tmp")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(link)


class InstallTransaction:
    """Stage a complete release before changing ``current``."""

    def __init__(self, paths: InstallerPaths, *, release_version: str) -> None:
        self.paths = paths
        self.release_version = release_version
        self.stage_dir = paths.staging_dir / f"release-{uuid4().hex}"
        self.snapshot: TransactionSnapshot | None = None
        self.backups: list[FileBackup] = []
        self._committed = False

    def __enter__(self) -> InstallTransaction:  # noqa: PYI034
        ensure_private_dir(self.stage_dir)
        return self

    def copy_bundle(self, bundle: str | Path) -> Path:
        source = Path(bundle).expanduser()
        if not source.is_dir():
            raise TransactionError(
                f"bundle staging source is not a directory: {source}"
            )
        destination = self.stage_dir / "bundle"
        try:
            shutil.copytree(source, destination, symlinks=True)
        except OSError as exc:
            raise TransactionError("cannot stage platform bundle") from exc
        return destination

    def write_marker(self, payload: dict[str, object]) -> None:
        marker = self.stage_dir / "staging.json"
        marker.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(marker, 0o600)

    def backup_file(self, path: str | Path) -> None:
        target = Path(path).expanduser()
        if any(item.path == target for item in self.backups):
            return
        if target.is_file():
            self.backups.append(
                FileBackup(
                    target,
                    True,
                    target.read_bytes(),
                    target.stat().st_mode & 0o777,
                )
            )
        else:
            self.backups.append(FileBackup(target, False))

    def restore_backups(self) -> None:
        for backup in reversed(self.backups):
            if backup.existed:
                backup.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                backup.path.write_bytes(backup.content)
                os.chmod(backup.path, backup.mode)
            else:
                backup.path.unlink(missing_ok=True)

    def commit(
        self, *, staged_bundle: str | Path, switch_current: bool = True
    ) -> TransactionSnapshot:
        source = Path(staged_bundle).expanduser()
        release_dir = self.paths.release_dir(self.release_version)
        if release_dir.exists():
            raise TransactionError(f"release already exists: {release_dir}")
        previous_target: str | None = None
        if self.paths.current_link.is_symlink():
            previous_target = os.readlink(self.paths.current_link)
        try:
            release_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.replace(source, release_dir)
            self.snapshot = TransactionSnapshot(
                self.release_version,
                release_dir,
                previous_target,
                current_switched=False,
            )
            self._committed = True
            if switch_current:
                self.switch_current()
            return self.snapshot
        except OSError as exc:
            raise TransactionError("release commit failed") from exc

    def switch_current(self) -> None:
        if self.snapshot is None:
            raise TransactionError("cannot switch current before release commit")
        if self.snapshot.current_switched:
            return
        try:
            _atomic_symlink(self.snapshot.release_dir, self.paths.current_link)
            self.snapshot.current_switched = True
        except OSError as exc:
            raise TransactionError("current release switch failed") from exc

    def rollback(self) -> None:
        snapshot = self.snapshot
        try:
            if snapshot is not None and snapshot.current_switched:
                if snapshot.previous_target is None:
                    self.paths.current_link.unlink(missing_ok=True)
                else:
                    _atomic_symlink(
                        Path(snapshot.previous_target), self.paths.current_link
                    )
                snapshot.current_switched = False
            if snapshot is not None:
                shutil.rmtree(snapshot.release_dir, ignore_errors=True)
        except OSError as exc:
            raise TransactionError("release rollback failed") from exc
        finally:
            self._committed = False

    def cleanup(self) -> None:
        shutil.rmtree(self.stage_dir, ignore_errors=True)

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if exc_type is not None and self._committed:
            self.rollback()
        self.cleanup()


def atomic_copy_file(
    source: str | Path, destination: str | Path, *, mode: int = 0o600
) -> Path:
    source_path = Path(source).expanduser()
    destination_path = Path(destination).expanduser()
    destination_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination_path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            with source_path.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        temporary.replace(destination_path)
        os.chmod(destination_path, mode)
        return destination_path
    except OSError as exc:
        raise TransactionError(f"cannot atomically copy {source_path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


__all__ = [
    "FileBackup",
    "InstallTransaction",
    "TransactionSnapshot",
    "atomic_copy_file",
]
