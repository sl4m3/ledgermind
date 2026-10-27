"""Core-owned backup/restore IPC contracts and maintenance runner.

This module deliberately contains no SQLite access.  The Core process owns its
knowledge store; Local only exchanges opaque Core snapshot artifacts through
``exchange/incoming`` and ``exchange/outgoing``.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .isolation import IsolationRequirements
from .compatibility import SUPPORTED_KNOWLEDGE_SCHEMA_MAX
from .sandbox import SandboxPlan, build_sandbox_plan
from .signing import CoreBinaryVerification, verify_core_binary

CORE_KNOWLEDGE_SCHEMA_VERSION = SUPPORTED_KNOWLEDGE_SCHEMA_MAX
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def _strict_mapping(payload: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {sorted(unknown)}")


def _validate_sha256(value: object) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError("sha256 must be a lowercase sha256 digest")
    return value


def _validate_backup_manifest_path(value: object) -> str:
    text = _required_text(value, "relative_path")
    if "\\" in text or "\x00" in text:
        raise ValueError("relative_path must use safe POSIX separators")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative_path must not escape the Core exchange directory")
    if path.parts[:2] not in {("exchange", "incoming"), ("exchange", "outgoing")}:
        raise ValueError("relative_path must be below exchange/incoming or exchange/outgoing")
    if len(path.parts) < 3:
        raise ValueError("relative_path must name an exchange artifact")
    return text


def _validate_exchange_path(value: object, *, directory: str) -> str:
    text = _required_text(value, "relative_path")
    if "\\" in text or "\x00" in text:
        raise ValueError("relative_path must use safe POSIX separators")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative_path must not escape the Core exchange directory")
    expected_prefix = ("exchange", directory)
    if path.parts[:2] != expected_prefix or len(path.parts) < 3:
        raise ValueError(f"relative_path must be below exchange/{directory}")
    return text


def _validate_restore_identifier(value: object, name: str) -> str:
    text = _required_text(value, name)
    if len(text) > 256 or ".." in text or any(character in text for character in ("/", "\\", "\x00")):
        raise ValueError(f"{name} contains an unsafe character")
    return text


def sha256_file(path: str | Path) -> str:
    """Return the wire-format digest of an opaque exchange artifact."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


@dataclass(frozen=True, slots=True)
class CreateBackupCommand:
    request_id: str

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")

    def to_payload(self) -> dict[str, object]:
        return {}


@dataclass(frozen=True, slots=True)
class BackupManifest:
    relative_path: str
    sha256: str
    size_bytes: int
    schema_version: int

    def __post_init__(self) -> None:
        _validate_backup_manifest_path(self.relative_path)
        _validate_sha256(self.sha256)
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        if self.schema_version != CORE_KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError("schema_version does not match the Core contract")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> BackupManifest:
        _strict_mapping(
            payload,
            {"relative_path", "sha256", "size_bytes", "schema_version"},
            "backup manifest",
        )
        return cls(
            relative_path=payload["relative_path"],
            sha256=payload["sha256"],
            size_bytes=payload["size_bytes"],
            schema_version=payload["schema_version"],
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ValidateBackupCommand:
    request_id: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")
        _validate_exchange_path(self.relative_path, directory="incoming")
        _validate_sha256(self.sha256)

    def to_payload(self) -> dict[str, object]:
        return {"relative_path": self.relative_path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class PrepareRestoreCommand:
    request_id: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")
        _validate_exchange_path(self.relative_path, directory="incoming")
        _validate_sha256(self.sha256)

    def to_payload(self) -> dict[str, object]:
        return {"relative_path": self.relative_path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class PrepareRestoreResult:
    relative_path: str
    sha256: str
    size_bytes: int
    schema_version: int
    restore_token: str
    requires_restart: bool

    def __post_init__(self) -> None:
        _validate_exchange_path(self.relative_path, directory="incoming")
        _validate_sha256(self.sha256)
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        if self.schema_version != CORE_KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError("schema_version does not match the Core contract")
        _validate_restore_identifier(self.restore_token, "restore_token")
        if not isinstance(self.requires_restart, bool):
            raise TypeError("requires_restart must be a boolean")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> PrepareRestoreResult:
        _strict_mapping(
            payload,
            {
                "relative_path",
                "sha256",
                "size_bytes",
                "schema_version",
                "restore_token",
                "requires_restart",
            },
            "prepare restore result",
        )
        return cls(
            relative_path=payload["relative_path"],
            sha256=payload["sha256"],
            size_bytes=payload["size_bytes"],
            schema_version=payload["schema_version"],
            restore_token=payload["restore_token"],
            requires_restart=payload["requires_restart"],
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "schema_version": self.schema_version,
            "restore_token": self.restore_token,
            "requires_restart": self.requires_restart,
        }


@dataclass(frozen=True, slots=True)
class BeginRestoreCommand:
    request_id: str
    relative_path: str
    sha256: str
    restore_token: str

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")
        _validate_exchange_path(self.relative_path, directory="incoming")
        _validate_sha256(self.sha256)
        _validate_restore_identifier(self.restore_token, "restore_token")

    def to_payload(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "restore_token": self.restore_token,
        }


@dataclass(frozen=True, slots=True)
class BeginRestoreResult:
    restore_transaction_id: str
    relative_path: str
    sha256: str
    size_bytes: int
    schema_version: int
    state: str

    def __post_init__(self) -> None:
        _validate_restore_identifier(self.restore_transaction_id, "restore_transaction_id")
        _validate_exchange_path(self.relative_path, directory="incoming")
        _validate_sha256(self.sha256)
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        if self.schema_version != CORE_KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError("schema_version does not match the Core contract")
        if self.state not in {"applied_pending_commit", "committed", "rolled_back"}:
            raise ValueError("restore transaction state is invalid")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> BeginRestoreResult:
        _strict_mapping(
            payload,
            {
                "restore_transaction_id",
                "relative_path",
                "sha256",
                "size_bytes",
                "schema_version",
                "state",
            },
            "begin restore result",
        )
        return cls(
            restore_transaction_id=payload["restore_transaction_id"],
            relative_path=payload["relative_path"],
            sha256=payload["sha256"],
            size_bytes=payload["size_bytes"],
            schema_version=payload["schema_version"],
            state=payload["state"],
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "restore_transaction_id": self.restore_transaction_id,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "schema_version": self.schema_version,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class CommitRestoreCommand:
    request_id: str
    restore_transaction_id: str

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")
        _validate_restore_identifier(self.restore_transaction_id, "restore_transaction_id")

    def to_payload(self) -> dict[str, object]:
        return {"restore_transaction_id": self.restore_transaction_id}


@dataclass(frozen=True, slots=True)
class CommitRestoreResult:
    restore_transaction_id: str
    committed: bool
    state: str

    def __post_init__(self) -> None:
        _validate_restore_identifier(self.restore_transaction_id, "restore_transaction_id")
        if self.committed is not True or self.state != "committed":
            raise ValueError("commit restore result is invalid")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> CommitRestoreResult:
        _strict_mapping(
            payload,
            {"restore_transaction_id", "committed", "state"},
            "commit restore result",
        )
        return cls(
            restore_transaction_id=payload["restore_transaction_id"],
            committed=payload["committed"],
            state=payload["state"],
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "restore_transaction_id": self.restore_transaction_id,
            "committed": self.committed,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class RollbackRestoreCommand:
    request_id: str
    restore_transaction_id: str

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")
        _validate_restore_identifier(self.restore_transaction_id, "restore_transaction_id")

    def to_payload(self) -> dict[str, object]:
        return {"restore_transaction_id": self.restore_transaction_id}


@dataclass(frozen=True, slots=True)
class RollbackRestoreResult:
    restore_transaction_id: str
    rolled_back: bool
    state: str

    def __post_init__(self) -> None:
        _validate_restore_identifier(self.restore_transaction_id, "restore_transaction_id")
        if self.rolled_back is not True or self.state != "rolled_back":
            raise ValueError("rollback restore result is invalid")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RollbackRestoreResult:
        _strict_mapping(
            payload,
            {"restore_transaction_id", "rolled_back", "state"},
            "rollback restore result",
        )
        return cls(
            restore_transaction_id=payload["restore_transaction_id"],
            rolled_back=payload["rolled_back"],
            state=payload["state"],
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "restore_transaction_id": self.restore_transaction_id,
            "rolled_back": self.rolled_back,
            "state": self.state,
        }


class CoreRestoreError(RuntimeError):
    """A verified Core maintenance restore could not be completed."""


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
BinaryVerifier = Callable[..., CoreBinaryVerification]
SandboxBuilder = Callable[..., SandboxPlan]


class CoreMaintenanceRunner:
    """Apply a Core restore through the A2 sandbox without opening knowledge.db.

    The runner accepts lifecycle callbacks instead of reaching into the A2
    supervisor internals.  This keeps the B1 consumer testable and leaves
    process supervision and sandbox implementation ownership with A2.
    """

    def __init__(
        self,
        *,
        core_binary_path: str | Path,
        core_data_dir: str | Path,
        stop_gateway: Callable[[], None],
        start_gateway: Callable[[], None],
        health_check: Callable[[], object],
        signature_path: str | Path | None = None,
        public_key_path: str | Path | None = None,
        sandbox_builder: SandboxBuilder = build_sandbox_plan,
        command_runner: CommandRunner = subprocess.run,
        binary_verifier: BinaryVerifier | None = None,
        isolation_requirements: IsolationRequirements | None = None,
        runtime_paths: Sequence[str | Path] = (),
        rounds_database_path: str | Path | None = None,
    ) -> None:
        self.core_binary_path = Path(core_binary_path).expanduser()
        self.core_data_dir = Path(core_data_dir).expanduser()
        self.stop_gateway = stop_gateway
        self.start_gateway = start_gateway
        self.health_check = health_check
        self.signature_path = (
            Path(signature_path).expanduser() if signature_path is not None else None
        )
        self.public_key_path = (
            Path(public_key_path).expanduser() if public_key_path is not None else None
        )
        self.sandbox_builder = sandbox_builder
        self.command_runner = command_runner
        self.binary_verifier = binary_verifier
        self.isolation_requirements = isolation_requirements or IsolationRequirements(
            require_rounds_database_hidden=rounds_database_path is not None,
        )
        self.runtime_paths = tuple(Path(item).expanduser() for item in runtime_paths)
        self.rounds_database_path = (
            Path(rounds_database_path).expanduser()
            if rounds_database_path is not None
            else None
        )

    def _verify_binary(self) -> CoreBinaryVerification | None:
        if self.binary_verifier is not None:
            return self.binary_verifier(
                self.core_binary_path,
                signature_path=self.signature_path,
                public_key_path=self.public_key_path,
            )
        if self.signature_path is None or self.public_key_path is None:
            raise CoreRestoreError(
                "Core restore requires signature and public-key verification"
            )
        try:
            return verify_core_binary(
                self.core_binary_path,
                signature_path=self.signature_path,
                public_key_path=self.public_key_path,
            )
        except Exception as exc:
            raise CoreRestoreError("Core binary verification failed") from exc

    @staticmethod
    def _health_is_healthy(value: object) -> bool:
        if isinstance(value, Mapping):
            return value.get("healthy") is True
        return getattr(value, "healthy", False) is True

    def apply_restore(self, preparation: PrepareRestoreResult) -> None:
        """Run Core's atomic restore command and restore the normal gateway."""

        if not preparation.requires_restart:
            raise CoreRestoreError("Core restore preparation does not require restart")
        _validate_exchange_path(preparation.relative_path, directory="incoming")
        verification = self._verify_binary()
        if verification is None or not verification.signature_verified:
            raise CoreRestoreError("Core binary signature verification failed")
        command = (
            str(self.core_binary_path),
            "--apply-restore",
            preparation.relative_path,
            "--restore-token",
            preparation.restore_token,
        )
        sandbox_plan = self.sandbox_builder(
            command,
            core_data_dir=self.core_data_dir,
            blocked_data_dirs=(
                (self.rounds_database_path.parent,)
                if self.rounds_database_path is not None
                else ()
            ),
            rounds_database_path=self.rounds_database_path,
            runtime_paths=self.runtime_paths,
            binary_signature_verified=verification.signature_verified,
            requirements=self.isolation_requirements,
            strict=True,
        )
        stopped = False
        operation_error: BaseException | None = None
        try:
            self.stop_gateway()
            stopped = True
            completed = self.command_runner(
                sandbox_plan.command,
                cwd=self.core_data_dir,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or "").strip()
                raise CoreRestoreError(
                    "Core restore command failed"
                    + (f": {detail[:500]}" if detail else "")
                )
        except BaseException as exc:
            operation_error = exc
            raise
        finally:
            if stopped:
                try:
                    self.start_gateway()
                    if not self._health_is_healthy(self.health_check()):
                        raise CoreRestoreError("Core health check failed after restore")
                except BaseException as restart_error:
                    if operation_error is None:
                        if isinstance(restart_error, CoreRestoreError):
                            raise
                        raise CoreRestoreError(
                            "Core gateway restart failed"
                        ) from restart_error
                    add_note = getattr(operation_error, "add_note", None)
                    if callable(add_note):
                        add_note(
                            "Core gateway restart failed "
                            f"({type(restart_error).__name__})"
                        )


# The aliases keep the contract names aligned with the protocol package while
# retaining the shorter Local-facing names used by callers.
CoreBackupManifest = BackupManifest
CreateBackup = CreateBackupCommand
ValidateBackup = ValidateBackupCommand
PrepareRestore = PrepareRestoreCommand
BeginRestore = BeginRestoreCommand
CommitRestore = CommitRestoreCommand
RollbackRestore = RollbackRestoreCommand


__all__ = [
    "CORE_KNOWLEDGE_SCHEMA_VERSION",
    "BackupManifest",
    "BeginRestore",
    "BeginRestoreCommand",
    "BeginRestoreResult",
    "CommitRestore",
    "CommitRestoreCommand",
    "CommitRestoreResult",
    "CoreBackupManifest",
    "CoreMaintenanceRunner",
    "CoreRestoreError",
    "CreateBackup",
    "CreateBackupCommand",
    "PrepareRestore",
    "PrepareRestoreCommand",
    "PrepareRestoreResult",
    "RollbackRestore",
    "RollbackRestoreCommand",
    "RollbackRestoreResult",
    "ValidateBackup",
    "ValidateBackupCommand",
    "sha256_file",
]
