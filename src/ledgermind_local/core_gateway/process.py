"""CoreGateway adapter backed by the isolated process IPC."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, NoReturn

from .base import CoreGateway
from .compatibility import (
    SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
    SUPPORTED_PROTOCOL_MAX,
    compatibility_reason,
)
from .contracts import (
    ControlMaintenanceResult,
    CoreCapabilityError,
    CoreExecutionResult,
    CoreExecutionTask,
    CoreGatewayError,
    CoreHealth,
    DomainRejectedError,
    FailExecutionTaskCommand,
    FailExecutionTaskResult,
    IngestRawRoundCommand,
    IngestRawRoundResult,
    ObjectFacetStatistics,
    PollExecutionTasksCommand,
    PollExecutionTasksResult,
    RecordRetrievalOutcomeCommand,
    RetrieveContextCommand,
    RetrieveContextResult,
    RunControlMaintenanceCommand,
    SubmitExecutionResult,
    SubmitExecutionResultCommand,
    TransientCoreError,
)
from .maintenance import (
    BackupManifest,
    BeginRestoreCommand,
    BeginRestoreResult,
    CommitRestoreCommand,
    CommitRestoreResult,
    CreateBackupCommand,
    PrepareRestoreCommand,
    PrepareRestoreResult,
    RollbackRestoreCommand,
    RollbackRestoreResult,
    ValidateBackupCommand,
)
from .supervisor import (
    CoreSupervisor,
    CoreSupervisorError,
    CoreSupervisorRemoteError,
)

_CAPABILITY_REQUIREMENTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "base": (
        frozenset({"health"}),
        frozenset(),
    ),
    "execution_tasks": (
        frozenset(
            {
                "poll_execution_tasks",
                "submit_execution_result",
                "fail_execution_task",
            }
        ),
        frozenset(),
    ),
    "object_facet": (
        frozenset(
            {
                "ingest_raw_round",
                "poll_execution_tasks",
                "submit_execution_result",
                "fail_execution_task",
                "retrieve_context",
                "record_retrieval_outcome",
                "run_control_maintenance",
                "get_object_facet_statistics",
                "delete_memory_space",
            }
        ),
        frozenset(
            {
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
        ),
    ),
    "maintenance": (
        frozenset(
            {
                "create_backup",
                "validate_backup",
                "prepare_restore",
                "begin_restore",
                "commit_restore",
                "rollback_restore",
            }
        ),
        frozenset({"core_owned_backup", "coordinated_restore"}),
    ),
}

# Backwards-compatible import for maintenance callers.  New code should use
# the compatibility module directly.
CORE_KNOWLEDGE_SCHEMA_VERSION = SUPPORTED_KNOWLEDGE_SCHEMA_MAX


def _validate_retrieval_outcome_payload(payload: Mapping[str, Any]) -> None:
    allowed = {
        "schema_version",
        "retrieval_request_id",
        "candidate_value_ids",
        "delivered_value_ids",
        "created_at",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(
            f"retrieval outcome contains unknown fields: {sorted(unknown)}"
        )
    if payload.get("schema_version") != 2:
        raise ValueError("schema_version must be 2")
    for name in ("retrieval_request_id", "created_at"):
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must not be empty")
    from datetime import datetime

    try:
        parsed = datetime.fromisoformat(
            str(payload["created_at"]).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("created_at must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    candidates = payload.get("candidate_value_ids")
    delivered = payload.get("delivered_value_ids")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidate_value_ids must be a non-empty array")
    if not isinstance(delivered, list):
        raise TypeError("delivered_value_ids must be an array")
    if any(not isinstance(value, str) or not value.strip() for value in candidates):
        raise ValueError("candidate_value_ids must contain non-empty strings")
    if any(not isinstance(value, str) or not value.strip() for value in delivered):
        raise ValueError("delivered_value_ids must contain non-empty strings")
    if len(set(candidates)) != len(candidates) or len(set(delivered)) != len(delivered):
        raise ValueError("retrieval outcome IDs must be unique")
    if not set(delivered).issubset(set(candidates)):
        raise ValueError("delivered_value_ids must be a subset of candidates")


def _normalize_core_retrieval_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Remove Core-only retrieval provenance before the public protocol boundary.

    Core includes ``source_kind`` on retrieval items for durable audit and
    ranking diagnostics.  The Python wire protocol deliberately exposes the
    smaller public ContextView contract, so strict protocol validation must
    happen after this boundary normalization rather than treating the newer
    internal field as a malformed Core response.
    """

    normalized = dict(payload)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return normalized
    normalized_items: list[Any] = []
    for raw_item in raw_items:
        if isinstance(raw_item, Mapping):
            item = dict(raw_item)
            item.pop("source_kind", None)
            normalized_items.append(item)
        else:
            normalized_items.append(raw_item)
    normalized["items"] = normalized_items
    return normalized


class ProcessCoreGateway(CoreGateway):
    """Use a supervised Core process without importing the Python Core package."""

    def __init__(
        self,
        supervisor: CoreSupervisor,
        *,
        required_capabilities: Iterable[str] = (),
        required_operations: Iterable[str] = (),
    ) -> None:
        self._supervisor = supervisor
        self._required_capabilities = self._normalize_names(
            required_capabilities, "capability"
        )
        self._required_operations = self._normalize_names(
            required_operations, "operation"
        )
        if self._required_capabilities or self._required_operations:
            self._validate_capabilities()

    @staticmethod
    def _normalize_names(values: Iterable[str], label: str) -> tuple[str, ...]:
        names = tuple(values)
        if any(not isinstance(value, str) or not value.strip() for value in names):
            raise ValueError(f"{label} names must be non-empty strings")
        return tuple(dict.fromkeys(names))

    def require_capabilities(self, *capabilities: str) -> None:
        """Validate a feature at its consumer initialization boundary."""

        if len(capabilities) == 1 and not isinstance(capabilities[0], str):
            values = tuple(capabilities[0])
        else:
            values = capabilities
        names = self._normalize_names(values, "capability")
        current = getattr(self, "_required_capabilities", ())
        self._required_capabilities = tuple(dict.fromkeys((*current, *names)))
        self._validate_capabilities()

    def _fail_closed(self, error: CoreGatewayError) -> NoReturn:
        try:
            self._supervisor.close()
        finally:
            raise error

    def _validate_capabilities(self) -> None:
        requested = tuple(
            dict.fromkeys(
                (
                    *getattr(self, "_required_capabilities", ()),
                    *getattr(self, "_required_operations", ()),
                )
            )
        )
        required_operations = set(getattr(self, "_required_operations", ()))
        required_capability_flags: set[str] = set()
        for capability in getattr(self, "_required_capabilities", ()):
            try:
                operations, flags = _CAPABILITY_REQUIREMENTS[capability]
            except KeyError as exc:
                raise ValueError(f"unknown Core capability: {capability}") from exc
            required_operations.update(operations)
            required_capability_flags.update(flags)

        try:
            self._supervisor.start()
            handshake = self._supervisor.handshake_result
        except CoreGatewayError:
            raise
        except Exception as exc:
            raise TransientCoreError("Core capability handshake failed") from exc
        if not isinstance(handshake, Mapping):
            self._fail_closed(
                TransientCoreError("Core capability handshake is unavailable")
            )

        raw_operations = handshake.get("supported_operations", ())
        raw_flags = handshake.get("capabilities", {})
        if not isinstance(raw_operations, (list, tuple, set, frozenset)):
            self._fail_closed(
                TransientCoreError("Core capability operations are malformed")
            )
        if not isinstance(raw_flags, Mapping):
            self._fail_closed(TransientCoreError("Core capability flags are malformed"))
        advertised_schema = handshake.get("knowledge_schema_version")
        advertised_protocol = handshake.get("protocol_version")
        reason_code = compatibility_reason(advertised_protocol, advertised_schema)
        if reason_code is not None:
            self._fail_closed(
                CoreCapabilityError(
                    requested=requested,
                    reason_code=reason_code,
                    expected_protocol_version=SUPPORTED_PROTOCOL_MAX,
                    advertised_protocol_version=(
                        advertised_protocol
                        if isinstance(advertised_protocol, int)
                        and not isinstance(advertised_protocol, bool)
                        else None
                    ),
                    expected_schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
                    advertised_schema_version=(
                        advertised_schema
                        if isinstance(advertised_schema, int)
                        else None
                    ),
                )
            )
        advertised_operations = {
            operation for operation in raw_operations if isinstance(operation, str)
        }
        advertised_flags = {
            capability
            for capability, supported in raw_flags.items()
            if isinstance(capability, str) and supported is True
        }
        missing_operations = tuple(sorted(required_operations - advertised_operations))
        missing_flags = tuple(sorted(required_capability_flags - advertised_flags))
        if missing_operations or missing_flags:
            self._fail_closed(
                CoreCapabilityError(
                    requested=requested,
                    missing_operations=missing_operations,
                    missing_capabilities=missing_flags,
                )
            )

    @property
    def advertised_operations(self) -> frozenset[str]:
        """Return operations from the validated Core handshake."""

        handshake = self._supervisor.handshake_result
        if not isinstance(handshake, Mapping):
            return frozenset()
        raw = handshake.get("supported_operations", ())
        if not isinstance(raw, (list, tuple, set, frozenset)):
            return frozenset()
        return frozenset(item for item in raw if isinstance(item, str))

    @property
    def advertised_capabilities(self) -> frozenset[str]:
        """Return enabled feature flags from the Core handshake."""

        handshake = self._supervisor.handshake_result
        if not isinstance(handshake, Mapping):
            return frozenset()
        raw = handshake.get("capabilities", {})
        if not isinstance(raw, Mapping):
            return frozenset()
        return frozenset(
            capability
            for capability, supported in raw.items()
            if isinstance(capability, str) and supported is True
        )

    @property
    def advertised_schema_version(self) -> int | None:
        """Return the knowledge schema version from the validated handshake."""

        handshake = self._supervisor.handshake_result
        if not isinstance(handshake, Mapping):
            return None
        value = handshake.get("knowledge_schema_version")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @property
    def advertised_protocol_version(self) -> int | None:
        """Return the IPC protocol version from the validated handshake."""

        handshake = self._supervisor.handshake_result
        if not isinstance(handshake, Mapping):
            return None
        value = handshake.get("protocol_version")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def health(self) -> CoreHealth:
        try:
            result = self._supervisor.request("health", {})
        except CoreSupervisorError as exc:
            return CoreHealth(healthy=False, backend="process", detail=str(exc))
        return CoreHealth(
            healthy=bool(result.get("healthy", False)),
            backend="process",
            detail=str(result["detail"]) if result.get("detail") else None,
            protocol_version=(
                int(result["protocol_version"])
                if isinstance(result.get("protocol_version"), int)
                and not isinstance(result.get("protocol_version"), bool)
                else self.advertised_protocol_version
            ),
            schema_version=(
                int(result["schema_version"])
                if isinstance(result.get("schema_version"), int)
                and not isinstance(result.get("schema_version"), bool)
                else self.advertised_schema_version
            ),
        )

    def ingest_raw_round(self, command: IngestRawRoundCommand) -> IngestRawRoundResult:
        try:
            from ledgermind_protocol.object_facet import IngestRawRoundRequest

            request_payload: dict[str, object] = {
                "command_id": command.command_id,
                "idempotency_key": command.idempotency_key,
                "memory_space_id": command.memory_space_id,
                "raw_round": command.raw_round,
            }
            if command.resolution_context is not None:
                raw_context = dict(command.resolution_context)
                for name in ("project", "repository", "task", "conversation"):
                    identifier = f"{name}_id"
                    if identifier not in raw_context and name in raw_context:
                        raw_context[identifier] = raw_context[name]
                    raw_context.pop(name, None)
                raw_context.pop("context_origin", None)
                request_payload["resolution_context"] = raw_context
            if command.embedding_profile is not None:
                # The active embedding identity is Core-owned metadata, not a
                # provider credential.  Forward it on every ingest so a Core
                # process started without a prior control pass can still
                # schedule subject/value embeddings deterministically.
                request_payload["embedding_profile"] = dict(command.embedding_profile)
            request = IngestRawRoundRequest.model_validate(request_payload)
        except (ImportError, TypeError, ValueError) as exc:
            raise DomainRejectedError("invalid_raw_round", str(exc)) from exc
        result = self._request(
            "ingest_raw_round",
            request.model_dump(mode="json"),
            request_id=command.command_id,
        )
        raw_round_id = result.get("raw_round_id")
        duplicate = result.get("duplicate")
        status = result.get("status")
        if (
            not isinstance(raw_round_id, str)
            or not raw_round_id.strip()
            or not isinstance(duplicate, bool)
            or not isinstance(status, str)
            or not status.strip()
        ):
            raise TransientCoreError("Core RawRound acceptance result is malformed")
        return IngestRawRoundResult(
            accepted=True,
            duplicate=duplicate,
            core_raw_round_id=raw_round_id,
            result_json=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
        )

    def retrieve_context(
        self, request: RetrieveContextCommand
    ) -> RetrieveContextResult:
        payload = request.to_payload()
        result = self._request(
            "retrieve_context",
            payload,
            request_id=request.request_id,
        )
        try:
            from ledgermind_protocol.object_facet import RetrievalResponse

            validated_result = RetrievalResponse.model_validate(
                _normalize_core_retrieval_payload(result)
            )
        except (ImportError, TypeError, ValueError) as exc:
            raise TransientCoreError("Core retrieval result is malformed") from exc
        return RetrieveContextResult(validated_result.model_dump(mode="json"))

    def record_retrieval_outcome(self, command: RecordRetrievalOutcomeCommand) -> None:
        payload = command.to_payload()
        try:
            from datetime import datetime, timezone

            created_at = datetime.now(timezone.utc).isoformat()
            _validate_retrieval_outcome_payload({**payload, "created_at": created_at})
        except (TypeError, ValueError) as exc:
            raise DomainRejectedError("invalid_retrieval_outcome", str(exc)) from exc
        self._request(
            "record_retrieval_outcome",
            {**payload, "created_at": created_at},
            request_id=command.request_id,
        )

    def run_control_maintenance(
        self, command: RunControlMaintenanceCommand
    ) -> ControlMaintenanceResult:
        result = self._request(
            "run_control_maintenance",
            command.to_payload(),
            request_id=command.request_id,
        )
        try:
            return ControlMaintenanceResult.from_payload(result)
        except (TypeError, ValueError) as exc:
            raise TransientCoreError(
                "Core control maintenance result is malformed"
            ) from exc

    def get_object_facet_statistics(self, request_id: str) -> ObjectFacetStatistics:
        result = self._request(
            "get_object_facet_statistics",
            {},
            request_id=request_id,
        )
        try:
            return ObjectFacetStatistics.from_payload(result)
        except (TypeError, ValueError) as exc:
            raise TransientCoreError(
                "Core object-facet statistics are malformed"
            ) from exc

    def try_get_object_facet_statistics(
        self,
        request_id: str,
        *,
        lock_timeout_seconds: float = 0.05,
        operation_timeout_seconds: float = 1.5,
    ) -> ObjectFacetStatistics:
        """Read content-free activity without waiting behind normal Core work."""

        result = self._supervisor.try_request(
            "get_object_facet_statistics",
            {},
            request_id=request_id,
            lock_timeout_seconds=lock_timeout_seconds,
            operation_timeout_seconds=operation_timeout_seconds,
        )
        try:
            return ObjectFacetStatistics.from_payload(result)
        except (TypeError, ValueError) as exc:
            raise TransientCoreError(
                "Core object-facet statistics are malformed"
            ) from exc

    def get_object_facet_snapshot(
        self,
        memory_space_id: str,
        request_id: str,
        *,
        cursor: str | None = None,
        page_size: int = 10_000,
    ) -> dict[str, Any]:
        if not memory_space_id.strip():
            raise ValueError("memory_space_id must not be empty")
        if not 1 <= page_size <= 10_000:
            raise ValueError("page_size must be between 1 and 10000")
        payload: dict[str, Any] = {
            "include_projection": True,
            "memory_space_id": memory_space_id,
            "page_size": page_size,
        }
        if cursor is not None:
            payload["cursor"] = cursor
        result = self._request(
            "get_object_facet_statistics",
            payload,
            request_id=request_id,
        )
        if (
            result.get("schema_version") != 2
            or not isinstance(result.get("snapshot"), dict)
            or not isinstance(result.get("page"), dict)
        ):
            raise TransientCoreError("Core knowledge projection is malformed")
        snapshot = result["snapshot"]
        page = result["page"]
        if (
            snapshot.get("schema_version") != 1
            or snapshot.get("memory_space_id") != memory_space_id
            or not isinstance(page.get("item_count"), int)
            or not isinstance(page.get("total_items"), int)
            or not isinstance(page.get("complete"), bool)
            or not isinstance(page.get("cursor"), str)
            or (
                page.get("next_cursor") is not None
                and not isinstance(page.get("next_cursor"), str)
            )
        ):
            raise TransientCoreError("Core knowledge projection is malformed")
        return result

    def delete_memory_space(self, memory_space_id: str, request_id: str) -> bool:
        if not memory_space_id.strip():
            raise ValueError("memory_space_id must not be empty")
        result = self._request(
            "delete_memory_space",
            {"memory_space_id": memory_space_id},
            request_id=request_id,
        )
        if not isinstance(result.get("deleted"), bool):
            raise TransientCoreError("Core memory-space deletion result is malformed")
        return bool(result["deleted"])

    def poll_execution_tasks(
        self, command: PollExecutionTasksCommand
    ) -> PollExecutionTasksResult:
        result = self._request(
            "poll_execution_tasks",
            command.to_payload(),
            request_id=command.request_id,
        )
        raw_tasks = result.get("tasks", [])
        if not isinstance(raw_tasks, list) or any(
            not isinstance(task, dict) for task in raw_tasks
        ):
            raise TransientCoreError("Core execution task result is malformed")
        try:
            tasks = tuple(
                CoreExecutionTask.from_payload(task).to_payload() for task in raw_tasks
            )
        except (TypeError, ValueError) as exc:
            raise TransientCoreError("Core execution task is malformed") from exc
        has_more = result.get("has_more", False)
        if not isinstance(has_more, bool):
            raise TransientCoreError("Core execution task pagination is malformed")
        return PollExecutionTasksResult(tasks=tasks, has_more=has_more)

    def submit_execution_result(
        self, command: SubmitExecutionResultCommand
    ) -> SubmitExecutionResult:
        try:
            strict_result = CoreExecutionResult.from_payload(command.result)
        except (TypeError, ValueError) as exc:
            raise DomainRejectedError("invalid_execution_result", str(exc)) from exc
        if strict_result.task_id != command.task_id:
            raise DomainRejectedError(
                "invalid_execution_result",
                "result.task_id does not match the submitted task",
            )
        result = self._request(
            "submit_execution_result",
            {
                **command.to_payload(),
                "result": strict_result.to_payload(),
            },
            request_id=command.request_id,
        )
        accepted = result.get("accepted")
        duplicate = result.get("duplicate", False)
        status = result.get("status", "accepted")
        if (
            not isinstance(accepted, bool)
            or not isinstance(duplicate, bool)
            or not isinstance(status, str)
        ):
            raise TransientCoreError(
                "Core execution result acknowledgement is malformed"
            )
        return SubmitExecutionResult(
            accepted=accepted, duplicate=duplicate, status=status
        )

    def fail_execution_task(
        self, command: FailExecutionTaskCommand
    ) -> FailExecutionTaskResult:
        result = self._request(
            "fail_execution_task",
            command.to_payload(),
            request_id=command.request_id,
        )
        return FailExecutionTaskResult(
            released=bool(result.get("released", result.get("accepted", False))),
            retry_scheduled=bool(result.get("retry_scheduled", False)),
            terminal=bool(result.get("terminal", False)),
            status=str(result.get("status", "failed")),
        )

    def create_backup(self, command: CreateBackupCommand) -> BackupManifest:
        result = self._request(
            "create_backup",
            command.to_payload(),
            request_id=command.request_id,
        )
        try:
            return BackupManifest.from_payload(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise TransientCoreError("Core backup result is malformed") from exc

    def validate_backup(self, command: ValidateBackupCommand) -> BackupManifest:
        result = self._request(
            "validate_backup",
            command.to_payload(),
            request_id=command.request_id,
        )
        try:
            return BackupManifest.from_payload(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise TransientCoreError(
                "Core backup validation result is malformed"
            ) from exc

    def prepare_restore(self, command: PrepareRestoreCommand) -> PrepareRestoreResult:
        result = self._request(
            "prepare_restore",
            command.to_payload(),
            request_id=command.request_id,
        )
        try:
            return PrepareRestoreResult.from_payload(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise TransientCoreError(
                "Core restore preparation result is malformed"
            ) from exc

    def begin_restore(self, command: BeginRestoreCommand) -> BeginRestoreResult:
        result = self._request(
            "begin_restore",
            command.to_payload(),
            request_id=command.request_id,
        )
        try:
            return BeginRestoreResult.from_payload(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise TransientCoreError("Core restore begin result is malformed") from exc

    def commit_restore(self, command: CommitRestoreCommand) -> CommitRestoreResult:
        result = self._request(
            "commit_restore",
            command.to_payload(),
            request_id=command.request_id,
        )
        try:
            return CommitRestoreResult.from_payload(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise TransientCoreError("Core restore commit result is malformed") from exc

    def rollback_restore(
        self, command: RollbackRestoreCommand
    ) -> RollbackRestoreResult:
        result = self._request(
            "rollback_restore",
            command.to_payload(),
            request_id=command.request_id,
        )
        try:
            return RollbackRestoreResult.from_payload(result)
        except (KeyError, TypeError, ValueError) as exc:
            raise TransientCoreError(
                "Core restore rollback result is malformed"
            ) from exc

    def close(self) -> None:
        self._supervisor.close()

    def _request(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        try:
            return self._supervisor.request(
                operation,
                payload,
                request_id=request_id,
            )
        except CoreSupervisorRemoteError as exc:
            if exc.retryable:
                raise TransientCoreError(str(exc)) from exc
            raise DomainRejectedError(exc.code, exc.detail) from exc
        except CoreSupervisorError as exc:
            raise TransientCoreError(str(exc)) from exc
        except CoreGatewayError:
            raise
        except Exception as exc:
            raise TransientCoreError("Core process request failed") from exc


__all__ = ["ProcessCoreGateway"]
