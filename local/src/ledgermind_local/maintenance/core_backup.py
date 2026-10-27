"""Create and prepare backups without taking ownership of Core storage.

Only the Local-owned rounds database is opened here.  Core knowledge snapshots
are opaque files obtained from and returned to the Core exchange directories.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from ledgermind_local.core_gateway.base import CoreGateway
from ledgermind_local.core_gateway.maintenance import (
    BackupManifest,
    CreateBackupCommand,
    PrepareRestoreCommand,
    PrepareRestoreResult,
    ValidateBackupCommand,
    sha256_file,
)


class CoreBackupError(RuntimeError):
    """A Core-owned backup could not be created or prepared."""


@dataclass(frozen=True, slots=True)
class PreparedCoreRestore:
    """Validated restore inputs held outside the active Local databases."""

    archive_path: Path
    staging_dir: Path
    rounds_snapshot_path: Path
    core_exchange_path: Path
    preparation: PrepareRestoreResult

    @property
    def restore_token(self) -> str:
        return self.preparation.restore_token

    def cleanup(self) -> None:
        """Remove only the private staging and Core exchange artifact."""

        self.core_exchange_path.unlink(missing_ok=True)
        shutil.rmtree(self.staging_dir, ignore_errors=True)


class CoreBackupService:
    """Orchestrate Core snapshots and Local rounds snapshots as one archive."""

    def __init__(
        self,
        *,
        gateway: CoreGateway,
        core_data_dir: str | Path,
        rounds_database_path: str | Path,
        max_artifact_bytes: int = 2_000_000_000,
    ) -> None:
        if max_artifact_bytes <= 0:
            raise ValueError("max_artifact_bytes must be positive")
        self.gateway = gateway
        self.core_data_dir = Path(core_data_dir).expanduser()
        self.rounds_database_path = Path(rounds_database_path).expanduser()
        self.max_artifact_bytes = max_artifact_bytes
        require_capabilities = getattr(gateway, "require_capabilities", None)
        if callable(require_capabilities):
            require_capabilities("maintenance")

    def create_backup(self, destination: str | Path) -> Path:
        """Create a 0600 archive containing rounds.db and an opaque Core artifact."""

        core_source: Path | None = None
        operation_error: BaseException | None = None
        try:
            command = CreateBackupCommand(f"local-backup:{uuid.uuid4()}")
            core_manifest = self.gateway.create_backup(command)
            core_source = self._core_exchange_path(
                core_manifest.relative_path, directory="outgoing"
            )
            self._verify_manifest(core_source, core_manifest)
            if not self.rounds_database_path.is_file():
                raise CoreBackupError("Local rounds database is missing")

            archive_path = self._reserve_destination(destination)
            with tempfile.TemporaryDirectory(
                prefix=".core-backup-", dir=str(archive_path.parent)
            ) as temporary:
                staging = Path(temporary)
                rounds_snapshot = staging / "rounds.db"
                _sqlite_backup(self.rounds_database_path, rounds_snapshot)
                self._write_archive(
                    archive_path=archive_path,
                    rounds_snapshot=rounds_snapshot,
                    core_source=core_source,
                    core_manifest=core_manifest,
                )
            os.chmod(archive_path, 0o600)
            return archive_path
        except CoreBackupError as exc:
            operation_error = exc
            raise
        except Exception as exc:
            operation_error = exc
            raise CoreBackupError("Core backup creation failed") from exc
        except BaseException as exc:
            operation_error = exc
            raise
        finally:
            if core_source is not None:
                try:
                    core_source.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    if operation_error is None:
                        raise CoreBackupError(
                            "Core backup artifact cleanup failed"
                        ) from cleanup_error

    def prepare_restore(self, archive_path: str | Path) -> PreparedCoreRestore:
        """Validate an archive and ask Core to prepare its one-time restore token."""

        source = Path(archive_path).expanduser()
        if not source.is_file():
            raise CoreBackupError("backup archive is missing")
        if not self.core_data_dir.is_dir():
            raise CoreBackupError("Core data directory is missing or not a directory")
        staging = Path(
            tempfile.mkdtemp(prefix=".core-restore-", dir=str(self.core_data_dir))
        )
        os.chmod(staging, 0o700)
        exchange_path: Path | None = None
        try:
            rounds_snapshot, core_source, core_manifest = self._extract_archive(
                source, staging
            )
            incoming_name = f"{uuid.uuid4().hex}-{core_source.name}"
            incoming_relative = f"exchange/incoming/{incoming_name}"
            exchange_path = self._core_exchange_path(
                incoming_relative, directory="incoming"
            )
            _atomic_copy(core_source, exchange_path)
            actual_manifest = BackupManifest(
                relative_path=incoming_relative,
                sha256=sha256_file(exchange_path),
                size_bytes=exchange_path.stat().st_size,
                schema_version=core_manifest.schema_version,
            )
            if actual_manifest.sha256 != core_manifest.sha256:
                raise CoreBackupError("Core backup digest changed during staging")
            validated = self.gateway.validate_backup(
                ValidateBackupCommand(
                    request_id=f"local-validate:{uuid.uuid4()}",
                    relative_path=incoming_relative,
                    sha256=core_manifest.sha256,
                )
            )
            self._assert_same_manifest(validated, actual_manifest)
            preparation = self.gateway.prepare_restore(
                PrepareRestoreCommand(
                    request_id=f"local-prepare:{uuid.uuid4()}",
                    relative_path=incoming_relative,
                    sha256=core_manifest.sha256,
                )
            )
            self._assert_preparation(preparation, actual_manifest)
            return PreparedCoreRestore(
                archive_path=source,
                staging_dir=staging,
                rounds_snapshot_path=rounds_snapshot,
                core_exchange_path=exchange_path,
                preparation=preparation,
            )
        except CoreBackupError:
            if exchange_path is not None:
                exchange_path.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)
            raise
        except Exception as exc:
            if exchange_path is not None:
                exchange_path.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)
            raise CoreBackupError("Core restore preparation failed") from exc

    # Explicit names make the orchestration seam usable by future CLI/API code
    # without accepting a path to a Core-owned working database.
    create_backup_archive = create_backup
    prepare_core_restore = prepare_restore

    def _core_exchange_path(self, relative_path: str, *, directory: str) -> Path:
        relative = PurePosixPath(relative_path)
        if relative.parts[:2] != ("exchange", directory) or len(relative.parts) < 3:
            raise CoreBackupError("Core returned an invalid exchange path")
        root = self.core_data_dir.resolve()
        exchange_root = (root / "exchange" / directory).resolve()
        candidate = (root / Path(*relative.parts)).resolve()
        try:
            candidate.relative_to(exchange_root)
        except ValueError as exc:
            raise CoreBackupError("Core exchange path escapes its allowed directory") from exc
        return candidate

    def _verify_manifest(self, path: Path, manifest: BackupManifest) -> None:
        if not path.is_file():
            raise CoreBackupError("Core backup artifact is missing")
        size = path.stat().st_size
        if size > self.max_artifact_bytes:
            raise CoreBackupError("Core backup artifact exceeds the configured limit")
        if size != manifest.size_bytes or sha256_file(path) != manifest.sha256:
            raise CoreBackupError("Core backup artifact digest or size mismatch")

    def _reserve_destination(self, destination: str | Path) -> Path:
        target = Path(destination).expanduser()
        if target.suffix.lower() != ".zip":
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            target = target / f"ledgermind-core-backup-{timestamp}-{uuid.uuid4().hex}.zip"
        else:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.exists():
            raise CoreBackupError("backup destination already exists")
        return target

    def _write_archive(
        self,
        *,
        archive_path: Path,
        rounds_snapshot: Path,
        core_source: Path,
        core_manifest: BackupManifest,
    ) -> None:
        core_member = f"core_snapshot/{core_source.name}"
        manifest_payload = {
            "format": "ledgermind-local-core-backup",
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "core": core_manifest.to_payload(),
            "core_archive_member": core_member,
            "rounds_archive_member": "rounds.db",
        }
        temporary = archive_path.with_name(
            f".{archive_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                _write_zip_bytes(
                    archive,
                    "backup_manifest.json",
                    json.dumps(
                        manifest_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                )
                _write_zip_file(archive, "rounds.db", rounds_snapshot)
                _write_zip_file(archive, core_member, core_source)
            os.chmod(temporary, 0o600)
            os.replace(temporary, archive_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _extract_archive(
        self, source: Path, staging: Path
    ) -> tuple[Path, Path, BackupManifest]:
        try:
            with zipfile.ZipFile(source, "r") as archive:
                names = {info.filename for info in archive.infolist()}
                if "server.token" in names or "knowledge.db" in names:
                    raise CoreBackupError("backup contains a forbidden active Core artifact")
                if "backup_manifest.json" not in names or "rounds.db" not in names:
                    raise CoreBackupError("backup manifest or rounds snapshot is missing")
                manifest_payload = json.loads(
                    archive.read("backup_manifest.json").decode("utf-8")
                )
                if not isinstance(manifest_payload, dict):
                    raise CoreBackupError("backup manifest is malformed")
                if manifest_payload.get("format") != "ledgermind-local-core-backup":
                    raise CoreBackupError("unsupported backup format")
                if manifest_payload.get("schema_version") != 1:
                    raise CoreBackupError("unsupported backup schema version")
                core_payload = manifest_payload.get("core")
                if not isinstance(core_payload, Mapping):
                    raise CoreBackupError("Core backup manifest is malformed")
                core_manifest = BackupManifest.from_payload(core_payload)
                core_member = manifest_payload.get("core_archive_member")
                if not isinstance(core_member, str) or not _safe_member(core_member):
                    raise CoreBackupError("Core backup member is unsafe")
                expected_member = f"core_snapshot/{Path(core_manifest.relative_path).name}"
                if core_member != expected_member or core_member not in names:
                    raise CoreBackupError("Core backup member does not match its manifest")
                rounds_snapshot = staging / "rounds.db"
                _extract_member(archive, "rounds.db", rounds_snapshot, self.max_artifact_bytes)
                core_snapshot = staging / Path(core_member)
                _extract_member(archive, core_member, core_snapshot, self.max_artifact_bytes)
        except CoreBackupError:
            raise
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
            raise CoreBackupError("backup archive is malformed") from exc
        self._validate_rounds_snapshot(rounds_snapshot)
        self._verify_manifest(core_snapshot, core_manifest)
        return rounds_snapshot, core_snapshot, core_manifest

    @staticmethod
    def _validate_rounds_snapshot(path: Path) -> None:
        connection = sqlite3.connect(path)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            connection.close()
        if result is None or result[0] != "ok":
            raise CoreBackupError("rounds snapshot failed SQLite integrity check")

    @staticmethod
    def _assert_same_manifest(actual: BackupManifest, expected: BackupManifest) -> None:
        if (
            actual.sha256 != expected.sha256
            or actual.size_bytes != expected.size_bytes
            or actual.schema_version != expected.schema_version
        ):
            raise CoreBackupError("Core validation returned a different artifact")

    @staticmethod
    def _assert_preparation(
        preparation: PrepareRestoreResult, expected: BackupManifest
    ) -> None:
        if (
            preparation.sha256 != expected.sha256
            or preparation.size_bytes != expected.size_bytes
            or preparation.schema_version != expected.schema_version
            or preparation.relative_path != expected.relative_path
        ):
            raise CoreBackupError("Core restore preparation returned a different artifact")


def _safe_member(member: str) -> bool:
    path = PurePosixPath(member)
    return bool(member) and not path.is_absolute() and all(
        part not in {"", ".", ".."} for part in path.parts
    )


def _write_zip_bytes(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o600 & 0xFFFF) << 16
    archive.writestr(info, content)


def _write_zip_file(archive: zipfile.ZipFile, name: str, source: Path) -> None:
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o600 & 0xFFFF) << 16
    with source.open("rb") as stream:
        archive.writestr(info, stream.read())


def _extract_member(
    archive: zipfile.ZipFile, member: str, destination: Path, max_bytes: int
) -> None:
    if not _safe_member(member):
        raise CoreBackupError("backup member is unsafe")
    info = archive.getinfo(member)
    if info.file_size < 0 or info.file_size > max_bytes:
        raise CoreBackupError("backup member exceeds the configured limit")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    written = 0
    with archive.open(info, "r") as source, destination.open("wb") as target:
        while True:
            chunk = source.read(min(1024 * 1024, max_bytes - written + 1))
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raise CoreBackupError("backup member exceeds the configured limit")
            target.write(chunk)
    os.chmod(destination, 0o600)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as source_stream, temporary.open("wb") as target:
            shutil.copyfileobj(source_stream, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _sqlite_backup(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()


__all__ = ["CoreBackupError", "CoreBackupService", "PreparedCoreRestore"]
