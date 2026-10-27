"""Public Core IPC transport contracts for the object-facet runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, ClassVar

CORE_IPC_PROTOCOL_VERSION = 1
CORE_KNOWLEDGE_SCHEMA_VERSION = 1
CORE_IPC_CAPABILITIES = frozenset(
    {
        "coordinated_restore",
        "core_owned_backup",
        "object_facet_memory",
        "operational_pipeline",
        "strict_candidate_binding",
        "generic_execution_tasks",
        "raw_round_ingest",
        "context_retrieval",
        "context_provenance",
        "stable_sha256_digests",
        "object_resolution",
        "explainable_context",
        "control_contour",
    }
)
CORE_IPC_SUPPORTED_OPERATIONS = (
    "handshake",
    "health",
    "create_backup",
    "validate_backup",
    "prepare_restore",
    "begin_restore",
    "commit_restore",
    "rollback_restore",
    "ingest_raw_round",
    "poll_execution_tasks",
    "submit_execution_result",
    "fail_execution_task",
    "retrieve_context",
    "record_retrieval_outcome",
    "run_control_maintenance",
    "get_object_facet_statistics",
    "delete_memory_space",
    "shutdown",
)
CORE_IPC_OPERATIONS = frozenset(CORE_IPC_SUPPORTED_OPERATIONS)
CORE_IPC_ERROR_CODES = (
    "INVALID_REQUEST",
    "IDEMPOTENCY_CONFLICT",
    "MEMORY_SPACE_MISMATCH",
    "NOT_FOUND",
    "VERSION_CONFLICT",
    "INTEGRITY_VIOLATION",
    "STALE_MODEL_TASK",
    "PROTOCOL_VERSION_UNSUPPORTED",
    "STORAGE_UNAVAILABLE",
    "INTERNAL_ERROR",
    "INVALID_OBJECT_FACET_RESULT",
    "UNKNOWN_OBJECT_CANDIDATE",
    "UNKNOWN_FACET",
    "RAW_ROUND_CONFLICT",
    "VALUE_CONSOLIDATION_CONFLICT",
    "EMBEDDING_VERSION_MISMATCH",
    "OBJECT_IDENTITY_AMBIGUOUS",
    "OBJECT_SCOPE_MISMATCH",
    "OBJECT_ALIAS_NOT_IN_SOURCE",
    "OBJECT_CANDIDATE_NOT_OFFERED",
    "CONTOUR_JOB_STALE",
)


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def _require_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _require_rfc3339(value: str, name: str) -> str:
    _require_text(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be RFC3339") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return value


def _require_object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return dict(value)


def _strict_object(value: object, allowed: set[str], name: str) -> dict[str, Any]:
    payload = _require_object(value, name)
    unknown = set(payload) - allowed
    if unknown:
        names = ", ".join(sorted(str(item) for item in unknown))
        raise ValueError(f"{name} contains unknown fields: {names}")
    return payload


def _require_exchange_path(
    value: object,
    name: str,
    allowed_directories: set[str],
) -> str:
    text = _require_text(value, name)
    if "\\" in text or "\x00" in text:
        raise ValueError(f"{name} must use safe POSIX separators")
    path = PurePosixPath(text)
    parts = text.split("/")
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
        or len(parts) < 3
        or parts[0] != "exchange"
        or parts[1] not in allowed_directories
    ):
        raise ValueError(f"{name} must be below a Core exchange directory")
    return text


@dataclass(frozen=True, slots=True)
class CoreError:
    code: str
    message: str
    error_id: str
    retryable: bool

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or self.code not in CORE_IPC_ERROR_CODES:
            raise ValueError(f"unknown Core IPC error code: {self.code}")
        _require_text(self.message, "error message")
        _require_text(self.error_id, "error id")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a boolean")

    def to_payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "error_id": self.error_id,
            "retryable": self.retryable,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CoreError:
        payload = _strict_object(
            payload,
            {"code", "message", "error_id", "retryable"},
            "Core error",
        )
        return cls(
            code=payload["code"],
            message=payload["message"],
            error_id=payload["error_id"],
            retryable=payload["retryable"],
        )


@dataclass(frozen=True, slots=True)
class CoreRequestEnvelope:
    protocol_version: int
    request_id: str
    operation: str
    payload: dict[str, Any]

    _VERSION: ClassVar[int] = CORE_IPC_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        _require_integer(self.protocol_version, "protocol version")
        if self.protocol_version != self._VERSION:
            raise ValueError("unsupported Core IPC protocol version")
        _require_text(self.request_id, "request id")
        if not isinstance(self.operation, str):
            raise TypeError("operation must be a string")
        if self.operation not in CORE_IPC_OPERATIONS:
            raise ValueError(f"unsupported Core IPC operation: {self.operation}")
        if not isinstance(self.payload, dict):
            raise TypeError("request payload must be an object")

    def to_payload(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "operation": self.operation,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CoreRequestEnvelope:
        payload = _strict_object(
            payload,
            {"protocol_version", "request_id", "operation", "payload"},
            "request envelope",
        )
        return cls(
            protocol_version=_require_integer(payload["protocol_version"], "protocol version"),
            request_id=_require_text(payload["request_id"], "request id"),
            operation=_require_text(payload["operation"], "operation"),
            payload=_require_object(payload["payload"], "request payload"),
        )

    @classmethod
    def from_json(cls, payload_json: str) -> CoreRequestEnvelope:
        return cls.from_payload(_require_object(json.loads(payload_json), "request envelope"))


@dataclass(frozen=True, slots=True)
class CoreResponseEnvelope:
    protocol_version: int
    request_id: str
    status: str
    result: dict[str, Any] | None = None
    error: CoreError | None = None

    _VERSION: ClassVar[int] = CORE_IPC_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        _require_integer(self.protocol_version, "protocol version")
        if self.protocol_version != self._VERSION:
            raise ValueError("unsupported Core IPC protocol version")
        _require_text(self.request_id, "request id")
        if not isinstance(self.status, str):
            raise TypeError("response status must be a string")
        if self.status not in {"ok", "error"}:
            raise ValueError("response status must be ok or error")
        if self.status == "ok" and (self.result is None or self.error is not None):
            raise ValueError("successful response requires result and no error")
        if self.status == "ok" and not isinstance(self.result, dict):
            raise TypeError("successful response result must be an object")
        if self.status == "error" and (self.error is None or self.result is not None):
            raise ValueError("error response requires error and no result")
        if self.status == "error" and not isinstance(self.error, CoreError):
            raise TypeError("error response requires a CoreError")

    @classmethod
    def ok(cls, request_id: str, result: dict[str, Any]) -> CoreResponseEnvelope:
        return cls(
            protocol_version=CORE_IPC_PROTOCOL_VERSION,
            request_id=request_id,
            status="ok",
            result=dict(result),
        )

    @classmethod
    def from_error(cls, request_id: str, error: CoreError) -> CoreResponseEnvelope:
        return cls(
            protocol_version=CORE_IPC_PROTOCOL_VERSION,
            request_id=request_id,
            status="error",
            error=error,
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "status": self.status,
        }
        if self.status == "ok":
            payload["result"] = self.result
        else:
            payload["error"] = self.error.to_payload() if self.error is not None else None
        return payload

    def to_json(self) -> str:
        return json.dumps(
            self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CoreResponseEnvelope:
        payload = _strict_object(
            payload,
            {"protocol_version", "request_id", "status", "result", "error"},
            "response envelope",
        )
        status = _require_text(payload["status"], "response status")
        if status not in {"ok", "error"}:
            raise ValueError("response status must be ok or error")
        if status == "ok":
            if "error" in payload:
                raise ValueError("successful response cannot contain error")
            return cls(
                protocol_version=_require_integer(payload["protocol_version"], "protocol version"),
                request_id=_require_text(payload["request_id"], "request id"),
                status=status,
                result=_require_object(payload["result"], "response result"),
            )
        if "result" in payload:
            raise ValueError("error response cannot contain result")
        return cls(
            protocol_version=_require_integer(payload["protocol_version"], "protocol version"),
            request_id=_require_text(payload["request_id"], "request id"),
            status=status,
            error=CoreError.from_payload(_require_object(payload["error"], "response error")),
        )

    @classmethod
    def from_json(cls, payload_json: str) -> CoreResponseEnvelope:
        return cls.from_payload(_require_object(json.loads(payload_json), "response envelope"))


@dataclass(frozen=True, slots=True)
class HandshakeResultPayload:
    protocol_version: int
    core_version: str
    knowledge_schema_version: int
    supported_operations: tuple[str, ...]
    capabilities: dict[str, bool]

    def __post_init__(self) -> None:
        _require_integer(self.protocol_version, "protocol version")
        if self.protocol_version != CORE_IPC_PROTOCOL_VERSION:
            raise ValueError("unsupported Core IPC protocol version")
        _require_text(self.core_version, "core version")
        _require_integer(self.knowledge_schema_version, "knowledge schema version")
        if self.knowledge_schema_version != CORE_KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError("unsupported Core knowledge schema version")
        if not isinstance(self.supported_operations, tuple) or not all(
            isinstance(operation, str) for operation in self.supported_operations
        ):
            raise TypeError("supported operations must be a tuple of strings")
        if not self.supported_operations:
            raise ValueError("supported operations must not be empty")
        if len(set(self.supported_operations)) != len(self.supported_operations):
            raise ValueError("supported operations must be unique")
        if not set(self.supported_operations).issubset(CORE_IPC_OPERATIONS):
            raise ValueError("supported operations contain an unknown operation")
        if not isinstance(self.capabilities, dict):
            raise TypeError("handshake capabilities must be an object")
        if set(self.capabilities) != CORE_IPC_CAPABILITIES or not all(
            isinstance(value, bool) for value in self.capabilities.values()
        ):
            raise ValueError("handshake capabilities are invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "core_version": self.core_version,
            "knowledge_schema_version": self.knowledge_schema_version,
            "supported_operations": list(self.supported_operations),
            "capabilities": dict(self.capabilities),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> HandshakeResultPayload:
        payload = _strict_object(
            payload,
            {
                "protocol_version",
                "core_version",
                "knowledge_schema_version",
                "supported_operations",
                "capabilities",
            },
            "handshake result",
        )
        operations = payload.get("supported_operations")
        capabilities = payload.get("capabilities")
        if not isinstance(operations, list) or not all(isinstance(item, str) for item in operations):
            raise TypeError("supported_operations must be an array of strings")
        if not isinstance(capabilities, dict):
            raise TypeError("capabilities must be an object")
        return cls(
            protocol_version=_require_integer(payload["protocol_version"], "protocol version"),
            core_version=_require_text(payload["core_version"], "core version"),
            knowledge_schema_version=_require_integer(
                payload["knowledge_schema_version"], "knowledge schema version"
            ),
            supported_operations=tuple(operations),
            capabilities=dict(capabilities),
        )


@dataclass(frozen=True, slots=True)
class CreateBackupPayload:
    def to_payload(self) -> dict[str, object]:
        return {}

    @classmethod
    def from_payload(cls, payload: object) -> CreateBackupPayload:
        _strict_object(payload, set(), "create backup")
        return cls()


@dataclass(frozen=True, slots=True)
class ValidateBackupPayload:
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        _require_exchange_path(self.relative_path, "relative path", {"incoming"})
        _require_sha256(self.sha256)

    def to_payload(self) -> dict[str, object]:
        return {"relative_path": self.relative_path, "sha256": self.sha256}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ValidateBackupPayload:
        payload = _strict_object(payload, {"relative_path", "sha256"}, "validate backup")
        return cls(relative_path=payload["relative_path"], sha256=payload["sha256"])


@dataclass(frozen=True, slots=True)
class PrepareRestorePayload(ValidateBackupPayload):
    """Validate an incoming Core snapshot before a coordinated restore."""

    def __post_init__(self) -> None:
        ValidateBackupPayload.__post_init__(self)
        _require_exchange_path(self.relative_path, "relative path", {"incoming"})


@dataclass(frozen=True, slots=True)
class BackupManifestPayload:
    relative_path: str
    sha256: str
    size_bytes: int
    schema_version: int

    def __post_init__(self) -> None:
        _require_exchange_path(
            self.relative_path,
            "relative path",
            {"incoming", "outgoing"},
        )
        _require_sha256(self.sha256)
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an integer")
        if self.schema_version != CORE_KNOWLEDGE_SCHEMA_VERSION:
            raise ValueError("schema_version does not match the Core contract")

    def to_payload(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> BackupManifestPayload:
        payload = _strict_object(
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


@dataclass(frozen=True, slots=True)
class PrepareRestoreResultPayload(BackupManifestPayload):
    restore_token: str
    requires_restart: bool

    def __post_init__(self) -> None:
        BackupManifestPayload.__post_init__(self)
        _require_exchange_path(self.relative_path, "relative path", {"incoming"})
        _require_restore_identifier(self.restore_token, "restore token")
        if not isinstance(self.requires_restart, bool):
            raise TypeError("requires_restart must be a boolean")

    def to_payload(self) -> dict[str, object]:
        payload = BackupManifestPayload.to_payload(self)
        payload["restore_token"] = self.restore_token
        payload["requires_restart"] = self.requires_restart
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PrepareRestoreResultPayload:
        payload = _strict_object(
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


@dataclass(frozen=True, slots=True)
class BeginRestorePayload(PrepareRestorePayload):
    """Authorize and apply a prepared Core snapshot pending commit."""

    restore_token: str

    def __post_init__(self) -> None:
        PrepareRestorePayload.__post_init__(self)
        _require_restore_identifier(self.restore_token, "restore token")

    def to_payload(self) -> dict[str, object]:
        payload = PrepareRestorePayload.to_payload(self)
        payload["restore_token"] = self.restore_token
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> BeginRestorePayload:
        payload = _strict_object(
            payload,
            {"relative_path", "sha256", "restore_token"},
            "begin restore",
        )
        return cls(
            relative_path=payload["relative_path"],
            sha256=payload["sha256"],
            restore_token=payload["restore_token"],
        )


@dataclass(frozen=True, slots=True)
class BeginRestoreResultPayload(BackupManifestPayload):
    restore_transaction_id: str
    state: str

    def __post_init__(self) -> None:
        BackupManifestPayload.__post_init__(self)
        _require_exchange_path(self.relative_path, "relative path", {"incoming"})
        _require_restore_identifier(self.restore_transaction_id, "restore transaction id")
        if not isinstance(self.state, str):
            raise TypeError("restore transaction state must be a string")
        if self.state not in {"applied_pending_commit", "committed", "rolled_back"}:
            raise ValueError("restore transaction state is invalid")

    def to_payload(self) -> dict[str, object]:
        payload = BackupManifestPayload.to_payload(self)
        payload["restore_transaction_id"] = self.restore_transaction_id
        payload["state"] = self.state
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> BeginRestoreResultPayload:
        payload = _strict_object(
            payload,
            {
                "relative_path",
                "sha256",
                "size_bytes",
                "schema_version",
                "restore_transaction_id",
                "state",
            },
            "begin restore result",
        )
        return cls(
            relative_path=payload["relative_path"],
            sha256=payload["sha256"],
            size_bytes=payload["size_bytes"],
            schema_version=payload["schema_version"],
            restore_transaction_id=payload["restore_transaction_id"],
            state=payload["state"],
        )


@dataclass(frozen=True, slots=True)
class CommitRestorePayload:
    restore_transaction_id: str

    def __post_init__(self) -> None:
        _require_restore_identifier(self.restore_transaction_id, "restore transaction id")

    def to_payload(self) -> dict[str, object]:
        return {"restore_transaction_id": self.restore_transaction_id}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CommitRestorePayload:
        payload = _strict_object(
            payload,
            {"restore_transaction_id"},
            "commit restore",
        )
        return cls(restore_transaction_id=payload["restore_transaction_id"])


@dataclass(frozen=True, slots=True)
class CommitRestoreResultPayload:
    restore_transaction_id: str
    committed: bool
    state: str

    def __post_init__(self) -> None:
        _require_restore_identifier(self.restore_transaction_id, "restore transaction id")
        if not isinstance(self.committed, bool):
            raise TypeError("committed must be a boolean")
        if not isinstance(self.state, str):
            raise TypeError("commit restore state must be a string")
        if self.state != "committed":
            raise ValueError("commit restore result must be committed")

    def to_payload(self) -> dict[str, object]:
        return {
            "restore_transaction_id": self.restore_transaction_id,
            "committed": self.committed,
            "state": self.state,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CommitRestoreResultPayload:
        payload = _strict_object(
            payload,
            {"restore_transaction_id", "committed", "state"},
            "commit restore result",
        )
        return cls(
            restore_transaction_id=payload["restore_transaction_id"],
            committed=payload["committed"],
            state=payload["state"],
        )


@dataclass(frozen=True, slots=True)
class RollbackRestorePayload:
    restore_transaction_id: str

    def __post_init__(self) -> None:
        _require_restore_identifier(self.restore_transaction_id, "restore transaction id")

    def to_payload(self) -> dict[str, object]:
        return {"restore_transaction_id": self.restore_transaction_id}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RollbackRestorePayload:
        payload = _strict_object(
            payload,
            {"restore_transaction_id"},
            "rollback restore",
        )
        return cls(restore_transaction_id=payload["restore_transaction_id"])


@dataclass(frozen=True, slots=True)
class RollbackRestoreResultPayload:
    restore_transaction_id: str
    rolled_back: bool
    state: str

    def __post_init__(self) -> None:
        _require_restore_identifier(self.restore_transaction_id, "restore transaction id")
        if not isinstance(self.rolled_back, bool):
            raise TypeError("rolled_back must be a boolean")
        if not isinstance(self.state, str):
            raise TypeError("rollback restore state must be a string")
        if self.state != "rolled_back":
            raise ValueError("rollback restore result must be rolled_back")

    def to_payload(self) -> dict[str, object]:
        return {
            "restore_transaction_id": self.restore_transaction_id,
            "rolled_back": self.rolled_back,
            "state": self.state,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RollbackRestoreResultPayload:
        payload = _strict_object(
            payload,
            {"restore_transaction_id", "rolled_back", "state"},
            "rollback restore result",
        )
        return cls(
            restore_transaction_id=payload["restore_transaction_id"],
            rolled_back=payload["rolled_back"],
            state=payload["state"],
        )


def _require_sha256(value: object) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError("sha256 must be a lowercase sha256 digest")
    if any(char not in "0123456789abcdef" for char in value[7:]):
        raise ValueError("sha256 must be a lowercase sha256 digest")
    return value


def _require_restore_identifier(value: object, name: str) -> str:
    text = _require_text(value, name)
    if (
        len(text) > 256
        or text == "."
        or ".." in text
        or any(character in text for character in "/\\\x00")
    ):
        raise ValueError(f"{name} contains an unsafe character")
    return text


__all__ = [
    "CORE_IPC_CAPABILITIES",
    "CORE_IPC_ERROR_CODES",
    "CORE_IPC_OPERATIONS",
    "CORE_IPC_PROTOCOL_VERSION",
    "CORE_IPC_SUPPORTED_OPERATIONS",
    "CORE_KNOWLEDGE_SCHEMA_VERSION",
    "BackupManifestPayload",
    "BeginRestorePayload",
    "BeginRestoreResultPayload",
    "CommitRestorePayload",
    "CommitRestoreResultPayload",
    "CoreError",
    "CoreRequestEnvelope",
    "CoreResponseEnvelope",
    "CreateBackupPayload",
    "HandshakeResultPayload",
    "PrepareRestorePayload",
    "PrepareRestoreResultPayload",
    "RollbackRestorePayload",
    "RollbackRestoreResultPayload",
    "ValidateBackupPayload",
]
