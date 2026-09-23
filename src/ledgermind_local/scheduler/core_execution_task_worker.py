"""Local worker for generic Core execution tasks."""

from __future__ import annotations

import logging
import re
import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import cast

from ledgermind_local.core_gateway.base import CoreGateway
from ledgermind_local.core_gateway.contracts import (
    CoreExecutionTask,
    DomainRejectedError,
    FailExecutionTaskCommand,
    PollExecutionTasksCommand,
    SubmitExecutionResultCommand,
    TransientCoreError,
)
from ledgermind_local.embedding_purpose import validate_embedding_purpose
from ledgermind_inference.core_task_executor import (
    CoreTaskExecutor,
    EmbeddingRequestSpec,
    GenericExecutionTask,
    ModelRequestSpec,
)
from ledgermind_local.inference.profile_slots import ProfileSlot
from ledgermind_local.inference.profile_store import InferenceProfileStore
from ledgermind_inference.profiles import StructuredOutputMode
from ledgermind_inference.providers.base import (
    ChatMessage,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderTransportError,
    TransientProviderError,
)
from ledgermind_local.inference.secrets import SecretNotFoundError
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations as migrations

logger = logging.getLogger(__name__)

_SAFE_ERROR_CODES = frozenset(
    {
        "execution_error",
        "provider_timeout",
        "provider_transport_error",
        "provider_unavailable",
        "provider_configuration_error",
        "provider_secret_missing",
        "provider_error",
        "invalid_model_output",
        "invalid_provider_response",
        "invalid_json_response",
        "length_truncation",
        "schema_shape_failure",
        "semantic_validation_failure",
        "language_fidelity_failure",
        "grounding_failure",
        "invalid_request",
        "provider_capability_unverified",
        "secret_missing",
        "input_budget_exceeded",
        "output_budget_exceeded",
        "authentication_error",
        "configuration_error",
        "cancelled",
        "timeout",
        "transport_error",
        "transient_provider_error",
        "profile_not_found",
        "profile_disabled",
        "input_too_large",
        "embedding_provider_error",
        "embedding_request_error",
        "embedding_batch_too_large",
        "embedding_text_too_large",
        "embedding_non_finite",
        "embedding_dimension_mismatch",
        "embedding_model_error",
        "embedding_cache_schema_error",
        "profile_missing",
        "core_unavailable",
        "core_poll_error",
        "core_delivery_error",
        "core_rejected_command",
        "core_rejected_stale_execution_task",
        "core_rejected_version_conflict",
        "core_rejected_invalid_request",
        "core_rejected_not_found",
        "core_rejected_idempotency_conflict",
        "core_rejected_integrity_violation",
        "core_rejected_invalid_object_facet_result",
        "core_rejected_unknown_object_candidate",
        "core_rejected_unknown_facet",
        "core_rejected_raw_round_conflict",
        "core_rejected_value_consolidation_conflict",
        "core_rejected_embedding_version_mismatch",
        "core_rejected_object_identity_ambiguous",
        "core_rejected_object_scope_mismatch",
        "core_rejected_object_alias_not_in_source",
        "core_rejected_object_candidate_not_offered",
        "core_rejected_contour_job_stale",
        "core_rejected_round_semantic_output_shape_invalid",
        "core_rejected_round_semantic_user_provenance_invalid",
        "core_rejected_round_semantic_execution_provenance_invalid",
        "core_rejected_round_semantic_outcome_inconsistent",
        "core_rejected_round_semantic_cardinality_exceeded",
        "core_rejected_round_semantic_object_ref_invalid",
        "core_rejected_round_semantic_object_refs_duplicate",
        "core_rejected_round_semantic_object_label_invalid",
        "core_rejected_round_semantic_object_description_invalid",
        "core_rejected_round_semantic_object_grounding_missing",
        "core_rejected_round_semantic_technical_anchors_invalid",
        "core_rejected_round_semantic_claim_refs_duplicate",
        "core_rejected_round_semantic_claim_object_ref_invalid",
        "core_rejected_round_semantic_claim_object_unknown",
        "core_rejected_round_semantic_claim_content_invalid",
        "core_rejected_round_semantic_claim_evidence_missing",
        "core_rejected_round_semantic_claim_refs_invalid",
        "core_rejected_structured_contract_digest_missing",
        "core_rejected_structured_contract_digest_mismatch",
        "core_rejected_structured_contract_missing",
        "core_rejected_structured_contract_invalid",
        "core_rejected_structured_contract_mismatch",
        "core_rejected_semantic_task_input_missing",
        "core_rejected_semantic_task_input_invalid",
        "core_rejected_semantic_reference_map_missing",
        "core_rejected_semantic_reference_map_invalid",
        "core_rejected_structured_attempt_invalid",
        "retry_exhausted",
        "expired",
        "permanent_failure",
    }
)


_INVALID_REQUEST_REASON_MARKERS: tuple[tuple[str, str], ...] = (
    (
        "round_semantic_user_provenance_invalid:",
        "core_rejected_round_semantic_user_provenance_invalid",
    ),
    (
        "round_semantic_execution_provenance_invalid:",
        "core_rejected_round_semantic_execution_provenance_invalid",
    ),
    (
        "round semantic output shape is invalid:",
        "core_rejected_round_semantic_output_shape_invalid",
    ),
    (
        "round semantic outcome, abstention reason, and candidate arrays are inconsistent",
        "core_rejected_round_semantic_outcome_inconsistent",
    ),
    (
        "round semantic result exceeds its bounded cardinality",
        "core_rejected_round_semantic_cardinality_exceeded",
    ),
    (
        "round semantic object refs must be unique",
        "core_rejected_round_semantic_object_refs_duplicate",
    ),
    (
        "round semantic object ref",
        "core_rejected_round_semantic_object_ref_invalid",
    ),
    (
        "round object label",
        "core_rejected_round_semantic_object_label_invalid",
    ),
    (
        "round object description",
        "core_rejected_round_semantic_object_description_invalid",
    ),
    (
        "object_missing_grounding_refs:",
        "core_rejected_round_semantic_object_grounding_missing",
    ),
    (
        "round technical_anchors",
        "core_rejected_round_semantic_technical_anchors_invalid",
    ),
    (
        "round claim refs must be unique",
        "core_rejected_round_semantic_claim_refs_duplicate",
    ),
    (
        "round claim references unknown object ",
        "core_rejected_round_semantic_claim_object_unknown",
    ),
    (
        "round claim object ref",
        "core_rejected_round_semantic_claim_object_ref_invalid",
    ),
    (
        "round claim content",
        "core_rejected_round_semantic_claim_content_invalid",
    ),
    (
        "round claim requires user or execution evidence",
        "core_rejected_round_semantic_claim_evidence_missing",
    ),
    (
        "user_refs",
        "core_rejected_round_semantic_claim_refs_invalid",
    ),
    (
        "execution_refs",
        "core_rejected_round_semantic_claim_refs_invalid",
    ),
    (
        "user_condition_refs",
        "core_rejected_round_semantic_claim_refs_invalid",
    ),
    (
        "execution_condition_refs",
        "core_rejected_round_semantic_claim_refs_invalid",
    ),
    (
        "structured result must return the task contract digest",
        "core_rejected_structured_contract_digest_missing",
    ),
    (
        "returned contract digest ",
        "core_rejected_structured_contract_digest_mismatch",
    ),
    (
        "structured task is missing output_contract",
        "core_rejected_structured_contract_missing",
    ),
    (
        "structured task contract cannot be decoded:",
        "core_rejected_structured_contract_invalid",
    ),
    (
        "structured task contract is invalid:",
        "core_rejected_structured_contract_invalid",
    ),
    (
        "task has unexpected contract ",
        "core_rejected_structured_contract_mismatch",
    ),
    (
        " task is missing model input",
        "core_rejected_semantic_task_input_missing",
    ),
    (
        " input is invalid:",
        "core_rejected_semantic_task_input_invalid",
    ),
    (
        " task is missing reference map",
        "core_rejected_semantic_reference_map_missing",
    ),
    (
        " reference map is invalid:",
        "core_rejected_semantic_reference_map_invalid",
    ),
    (
        "structured generation attempt ",
        "core_rejected_structured_attempt_invalid",
    ),
)


def _core_rejection_error_code(exc: DomainRejectedError) -> str:
    """Return a bounded, content-free reason for a Core rejection.

    Core messages can contain task-local refs or validation text and therefore
    must not be persisted verbatim.  Known deterministic validation classes
    are projected onto stable reason codes; unknown messages retain only the
    public Core error code.
    """

    core_code = re.sub(r"[^a-z0-9]+", "_", exc.code.lower()).strip("_")
    if core_code == "invalid_request":
        detail = exc.detail.lower()
        for marker, reason_code in _INVALID_REQUEST_REASON_MARKERS:
            if marker in detail:
                return reason_code
    return _safe_error_code(
        f"core_rejected_{core_code or 'command'}",
        "core_rejected_command",
    )


def _safe_error_code(value: str | None, fallback: str = "execution_error") -> str:
    if value in _SAFE_ERROR_CODES:
        return value
    return fallback


class ExecutionFailureClassification:
    """Safe error code and retry policy sent back to Core."""

    def __init__(
        self, error_code: str, retryable: bool, retry_after_seconds: int = 60
    ) -> None:
        if not error_code.strip():
            raise ValueError("error_code must not be empty")
        if not 0 <= retry_after_seconds <= 86_400:
            raise ValueError("retry_after_seconds must be between 0 and 86400")
        if not retryable and retry_after_seconds != 0:
            raise ValueError("permanent failures must not request a retry delay")
        self.error_code = error_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


def classify_execution_error(exc: BaseException) -> ExecutionFailureClassification:
    """Classify provider/Core failures without serializing exception details."""

    code = getattr(exc, "code", None)
    if code == "input_budget_exceeded":
        return ExecutionFailureClassification("input_budget_exceeded", False, 0)
    if code in {
        "invalid_json_response",
        "invalid_request",
        "provider_capability_unverified",
        "secret_missing",
        "schema_shape_failure",
        "semantic_validation_failure",
        "language_fidelity_failure",
        "grounding_failure",
    }:
        return ExecutionFailureClassification(str(code), False, 0)
    if isinstance(exc, (ProviderTimeoutError, TimeoutError)):
        return ExecutionFailureClassification("provider_timeout", True)
    if isinstance(exc, (ProviderTransportError, ConnectionError, OSError)):
        return ExecutionFailureClassification("provider_transport_error", True)
    if isinstance(exc, TransientProviderError):
        return ExecutionFailureClassification("provider_unavailable", True)
    error_type = type(exc).__name__
    if error_type == "InferenceProfileNotFoundError":
        return ExecutionFailureClassification("profile_not_found", False, 0)
    if error_type == "InferenceProfileDisabledError":
        return ExecutionFailureClassification("profile_disabled", False, 0)
    if error_type == "InferenceInputTooLargeError":
        return ExecutionFailureClassification("input_too_large", False, 0)
    if error_type == "InferenceResponseValidationError":
        return ExecutionFailureClassification("invalid_model_output", False, 0)
    if isinstance(exc, (ProviderAuthenticationError, ProviderConfigurationError)):
        return ExecutionFailureClassification("provider_configuration_error", False, 0)
    if isinstance(exc, SecretNotFoundError):
        return ExecutionFailureClassification("provider_secret_missing", False, 0)
    if isinstance(exc, (ProviderResponseError, ValueError, TypeError)):
        return ExecutionFailureClassification("invalid_model_output", False, 0)
    if isinstance(exc, TransientCoreError):
        return ExecutionFailureClassification("core_unavailable", True)
    if isinstance(exc, DomainRejectedError):
        return ExecutionFailureClassification(
            _core_rejection_error_code(exc),
            False,
            0,
        )
    if isinstance(exc, ProviderError):
        return ExecutionFailureClassification("provider_error", False, 0)

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and (
        status_code == 429 or 500 <= status_code <= 599
    ):
        return ExecutionFailureClassification("provider_unavailable", True)
    message = str(exc).lower()
    if any(
        marker in message for marker in ("429", "temporar", "unavailable", "connection")
    ):
        return ExecutionFailureClassification("provider_unavailable", True)
    if "timeout" in message or "timed out" in message:
        return ExecutionFailureClassification("provider_timeout", True)
    if isinstance(exc, RuntimeError):
        return ExecutionFailureClassification("provider_error", False, 0)
    return ExecutionFailureClassification("execution_error", False, 0)


ConnectionFactory = Callable[[str | Path], sqlite3.Connection]


class CoreExecutionTaskWorker:
    """Execute generic Core tasks without interpreting operation metadata."""

    def __init__(
        self,
        *,
        database_path: str | Path,
        gateway: CoreGateway,
        executor: CoreTaskExecutor,
        worker_id: str,
        poll_limit: int = 10,
        lease_seconds: int = 300,
        connection_factory: ConnectionFactory = open_sqlite_connection,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if not 1 <= poll_limit <= 100:
            raise ValueError("poll_limit must be between 1 and 100")
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 1 and 3600")
        self._database_path = str(database_path)
        self._gateway = gateway
        self._executor = executor
        self._worker_id = worker_id
        self._poll_limit = poll_limit
        self._lease_seconds = lease_seconds
        self._connection_factory = connection_factory
        self._closed = False
        self._provider_circuit_open = False
        require_capabilities = getattr(gateway, "require_capabilities", None)
        if callable(require_capabilities):
            require_capabilities("execution_tasks")

    def process_once(self) -> int:
        if self._closed:
            raise RuntimeError("Core execution task worker is closed")
        if self._provider_circuit_open:
            return 0
        connection = self._connection_factory(self._database_path)
        try:
            migrations.apply_migrations(connection)
            # Migration helpers may leave a write transaction open.  Do not
            # retain that connection while executing provider work: embedding
            # execution uses a second connection for the persistent vector
            # cache and would otherwise wait on our own SQLite lock until the
            # provider-task timeout expires.
            connection.commit()
            spaces = connection.execute(
                "SELECT memory_space_id FROM memory_spaces ORDER BY memory_space_id"
            ).fetchall()
        finally:
            connection.close()

        processed = 0
        for row in spaces:
            memory_space_id = str(row[0])
            try:
                polled = self._gateway.poll_execution_tasks(
                    PollExecutionTasksCommand(
                        request_id=self._request_id("poll"),
                        memory_space_id=memory_space_id,
                        worker_id=self._worker_id,
                        limit=self._poll_limit,
                        lease_seconds=self._lease_seconds,
                    )
                )
            except Exception:  # noqa: BLE001 - isolate one space's backlog
                logger.warning(
                    "Core execution task poll failed",
                    extra={
                        "worker": self._worker_id,
                        "memory_space_id": memory_space_id,
                        "error_code": "core_poll_error",
                    },
                )
                continue
            processed += len(polled.tasks)
            self._process_tasks(polled.tasks, memory_space_id)
            if self._provider_circuit_open:
                break
        return processed

    @property
    def provider_circuit_open(self) -> bool:
        """Whether provider credentials/configuration stopped further task polling."""

        return self._provider_circuit_open

    def _open_provider_circuit_on_failure(self, result: object) -> None:
        if (
            getattr(result, "status", None) == "failed"
            and getattr(result, "error_code", None)
            in {
                "authentication_failed",
                "provider_configuration_error",
                "provider_secret_missing",
                "secret_missing",
            }
            and not self._provider_circuit_open
        ):
            self._provider_circuit_open = True
            logger.error(
                "provider configuration failure paused execution task polling until restart",
                extra={"worker": self._worker_id, "error_code": result.error_code},
            )

    def close(self) -> None:
        self._closed = True

    def _process_task(self, raw_task: dict[str, object], memory_space_id: str) -> None:
        try:
            task = execution_task_from_wire(raw_task, memory_space_id)
            result = self._executor.execute(task)
            self._open_provider_circuit_on_failure(result)
            self._deliver_result_with_structured_retry(task, result, memory_space_id)
        except Exception as exc:  # noqa: BLE001 - release every leased task
            self._fail_task(raw_task, memory_space_id, exc)

    def _process_tasks(
        self, raw_tasks: list[dict[str, object]], memory_space_id: str
    ) -> None:
        """Batch only compatible embedding tasks; keep one Core result per task."""

        converted: list[GenericExecutionTask] = []
        for raw_task in raw_tasks:
            try:
                converted.append(execution_task_from_wire(raw_task, memory_space_id))
            except Exception as exc:  # noqa: BLE001 - isolate malformed leases
                self._fail_task(raw_task, memory_space_id, exc)
        if not converted:
            return
        try:
            results = self._executor.execute_batch(tuple(converted))
        except Exception as exc:  # noqa: BLE001 - release every leased task
            for task in converted:
                self._fail_task(task.model_dump(mode="json"), memory_space_id, exc)
            return
        for task, result in zip(converted, results, strict=True):
            self._open_provider_circuit_on_failure(result)
            try:
                self._deliver_result_with_structured_retry(
                    task, result, memory_space_id
                )
            except Exception as exc:  # noqa: BLE001 - isolate delivery failures
                self._fail_task(task.model_dump(mode="json"), memory_space_id, exc)

    def _deliver_result_with_structured_retry(
        self,
        task: GenericExecutionTask,
        result: object,
        memory_space_id: str,
    ) -> None:
        """Give one structured generation a bounded contract retry.

        Local still dispatches only by technical task kind. A remote Core
        rejection can mean that a weak provider returned a Core-invalid
        structured answer; one bounded fresh generation is safe recovery.
        Local never inspects the opaque operation or edits the answer.
        """

        self._record_egress_audit(task, result, memory_space_id)

        # A provider can return a transiently malformed JSON/schema response
        # even when the transport succeeded.  Treat one such result as a
        # bounded structured-output recovery, just like a Core-side contract
        # rejection.  This branch is failure-only: a successful normal task
        # still consumes exactly one provider call.
        if (
            task.task_kind in {"generate_json", "object_resolution"}
            and getattr(result, "status", None) == "failed"
            and getattr(result, "error_code", None)
            in {
                "invalid_provider_response",
                "invalid_json_response",
                "invalid_model_output",
                "length_truncation",
                "schema_shape_failure",
            }
        ):
            logger.warning(
                "retrying structured generation after provider shape failure",
                extra={"worker": self._worker_id, "task_id": task.task_id},
            )
            retry_result = self._executor.execute(
                task,
                force_provider_fallback=True,
            )
            self._record_egress_audit(task, retry_result, memory_space_id)
            if getattr(retry_result, "status", None) == "completed":
                self._deliver_result(task, retry_result, memory_space_id)
                return
            result = retry_result

        try:
            self._deliver_result(task, result, memory_space_id)
        except DomainRejectedError as exc:
            if (
                task.task_kind not in {"generate_json", "object_resolution"}
                or exc.code == "invalid_execution_result"
            ):
                raise
            logger.warning(
                "retrying structured generation after remote Core rejection",
                extra={"worker": self._worker_id, "task_id": task.task_id},
            )
            retry_result = self._executor.execute(
                task,
                force_provider_fallback=True,
            )
            self._record_egress_audit(task, retry_result, memory_space_id)
            self._deliver_result(task, retry_result, memory_space_id)

    def _record_egress_audit(
        self,
        task: GenericExecutionTask,
        result: object,
        memory_space_id: str,
    ) -> None:
        """Persist one content-free executor attempt in the Local database."""

        audit = getattr(result, "egress_audit", None)
        if audit is None:
            return
        connection = self._connection_factory(self._database_path)
        try:
            migrations.apply_migrations(connection)
            InferenceProfileStore(connection).record_egress_audit(
                memory_space_id=memory_space_id,
                profile_id=getattr(audit, "profile_id", None),
                operation=task.operation or task.task_kind,
                provider_kind=getattr(audit, "provider", None) or "unknown",
                model=getattr(audit, "model", None) or "unknown",
                status=getattr(audit, "status", None)
                or getattr(result, "status", "unknown"),
                request_bytes=int(getattr(audit, "input_bytes", 0)),
                response_bytes=int(getattr(audit, "output_bytes", 0)),
                attempts=1,
                error_code=getattr(result, "error_code", None),
            )
            connection.commit()
        except Exception:  # noqa: BLE001 - diagnostics must not block delivery
            logger.warning(
                "could not persist content-free egress audit",
                extra={"worker": self._worker_id, "task_id": task.task_id},
            )
        finally:
            connection.close()

    def _deliver_result(
        self,
        task: GenericExecutionTask,
        result: object,
        memory_space_id: str,
    ) -> None:
        if not hasattr(result, "status"):
            raise ValueError("executor returned an invalid result")
        status = result.status
        if status == "completed":
            submitted = self._gateway.submit_execution_result(
                SubmitExecutionResultCommand(
                    request_id=self._request_id("submit"),
                    task_id=task.task_id,
                    memory_space_id=memory_space_id,
                    worker_id=self._worker_id,
                    result=core_result_payload(result),
                )
            )
            if not submitted.accepted:
                raise TransientCoreError("Core did not accept execution result")
            return
        retryable = execution_result_is_retryable(result)
        self._gateway.fail_execution_task(
            FailExecutionTaskCommand(
                request_id=self._request_id("fail"),
                task_id=task.task_id,
                memory_space_id=memory_space_id,
                worker_id=self._worker_id,
                error_code=_safe_error_code(result.error_code, result.status),
                retryable=retryable,
                retry_after_seconds=60 if retryable else 0,
            )
        )

    def _fail_task(
        self,
        raw_task: dict[str, object],
        memory_space_id: str,
        exc: BaseException,
    ) -> None:
        task_id = str(raw_task.get("task_id", "unknown"))
        classification = (
            classify_execution_error(exc)
            if isinstance(exc, Exception)
            else ExecutionFailureClassification("execution_error", False, 0)
        )
        detail = getattr(exc, "detail", None)
        if not isinstance(detail, str) or not detail.strip():
            detail = str(exc)
        detail = detail.strip().replace("\n", " ")[:500]
        logger.warning(
            "Core execution task failed: %s",
            detail,
            extra={
                "worker": self._worker_id,
                "task_id": task_id,
                "error_code": classification.error_code,
            },
        )
        self._gateway.fail_execution_task(
            FailExecutionTaskCommand(
                request_id=self._request_id("fail"),
                task_id=task_id,
                memory_space_id=memory_space_id,
                worker_id=self._worker_id,
                error_code=classification.error_code,
                retryable=classification.retryable,
                retry_after_seconds=classification.retry_after_seconds,
            )
        )

    def _request_id(self, operation: str) -> str:
        return f"{self._worker_id}:{operation}:{uuid.uuid4()}"


def core_result_payload(result: object) -> dict[str, object]:
    """Project the Local executor result onto the Core-owned wire contract."""

    payload = result.model_dump(mode="json")
    if payload.get("task_kind") == "embed_texts":
        embedding = payload.get("embedding_result")
        if isinstance(embedding, dict):
            # ``role`` and ``renderer_version`` are Local cache/rendering
            # metadata.  They are valid on the Local result but are not part
            # of Core's strict embedding-result contract.
            payload["embedding_result"] = {
                key: embedding[key]
                for key in (
                    "vectors",
                    "model",
                    "model_version",
                    "dimensions",
                    "purpose",
                )
                if key in embedding
            }
    return payload


def execution_result_is_retryable(result: object) -> bool:
    if getattr(result, "status", None) in {"timeout", "cancelled"}:
        return True
    return getattr(result, "error_code", None) in {
        "provider_timeout",
        "provider_transport_error",
        "provider_unavailable",
        "transport_error",
        "transient_provider_error",
        "timeout",
    }


# Compatibility aliases for tests and third-party Local extensions written
# before the transport-neutral helpers became part of the public worker API.
_core_result_payload = core_result_payload
_execution_result_is_retryable = execution_result_is_retryable


def execution_task_from_wire(
    raw_task: dict[str, object], memory_space_id: str
) -> GenericExecutionTask:
    """Convert the language-neutral wire task to the Local executor model."""

    wire = CoreExecutionTask.from_payload(raw_task)
    if wire.memory_space_id != memory_space_id:
        raise ValueError("execution task memory space does not match poll scope")
    model_request = None
    if wire.model_request is not None:
        model_request = ModelRequestSpec(
            messages=tuple(
                ChatMessage.model_validate(message)
                for message in wire.model_request.get("messages", [])
            ),
            max_output_tokens=int(wire.model_request["max_output_tokens"]),
            response_format=(
                {"type": wire.model_request["response_format"]}
                if isinstance(wire.model_request.get("response_format"), str)
                else (
                    dict(wire.model_request["response_format"])
                    if isinstance(wire.model_request.get("response_format"), dict)
                    else None
                )
            ),
            output_contract=(
                dict(wire.model_request["output_contract"])
                if isinstance(wire.model_request.get("output_contract"), dict)
                else None
            ),
            structured_output_requirement=(
                dict(wire.model_request["structured_output_requirement"])
                if isinstance(
                    wire.model_request.get("structured_output_requirement"), dict
                )
                else None
            ),
            mode=cast(
                StructuredOutputMode,
                str(
                    wire.model_request.get("mode")
                    or wire.model_request.get("structured_output_mode")
                    or (
                        "strict_json_schema"
                        if isinstance(
                            wire.model_request.get("structured_output_requirement"),
                            dict,
                        )
                        else "auto"
                    )
                ),
            ),
            tool_name=(
                str(wire.model_request["tool_name"])
                if wire.model_request.get("tool_name") is not None
                else None
            ),
            metadata=(
                dict(wire.model_request["metadata"])
                if isinstance(wire.model_request.get("metadata"), dict)
                else {}
            ),
            seed=(
                int(wire.model_request["seed"])
                if wire.model_request.get("seed") is not None
                else None
            ),
        )
    embedding_request = None
    if wire.embedding_request is not None:
        operation_input = wire.operation_input or {}

        def _request_or_operation_input(name: str, *fallback_names: str) -> object:
            value = wire.embedding_request.get(name)
            if value is not None:
                return value
            for fallback_name in fallback_names:
                value = operation_input.get(fallback_name)
                if value is not None:
                    return value
            return None

        embedding_request = EmbeddingRequestSpec(
            texts=tuple(str(text) for text in wire.embedding_request.get("texts", [])),
            purpose=validate_embedding_purpose(wire.embedding_request["purpose"]),
            subject_refs=(
                tuple(
                    str(subject_ref)
                    for subject_ref in wire.embedding_request["subject_refs"]
                )
                if isinstance(wire.embedding_request.get("subject_refs"), list)
                else None
            ),
            dimensions=(
                int(wire.embedding_request["dimensions"])
                if wire.embedding_request.get("dimensions") is not None
                else None
            ),
            profile_fingerprint=(
                str(value)
                if (
                    value := _request_or_operation_input(
                        "profile_fingerprint", "embedding_profile_fingerprint"
                    )
                )
                is not None
                else None
            ),
            config_fingerprint=(
                str(value)
                if (
                    value := _request_or_operation_input(
                        "config_fingerprint", "embedding_config_fingerprint"
                    )
                )
                is not None
                else None
            ),
            privacy_class=str(
                _request_or_operation_input("privacy_class") or "default"
            ),
            cache_namespace=str(_request_or_operation_input("cache_namespace") or ""),
            cache_keys=(
                tuple(str(key) for key in wire.embedding_request["cache_keys"])
                if isinstance(wire.embedding_request.get("cache_keys"), list)
                else None
            ),
            deadline=(
                str(value)
                if (value := _request_or_operation_input("deadline")) is not None
                else None
            ),
            role=(
                str(value)
                if (value := _request_or_operation_input("role", "embedding_role"))
                is not None
                else None
            ),
            renderer_version=(
                str(value)
                if (value := _request_or_operation_input("renderer_version"))
                is not None
                else None
            ),
        )
    return GenericExecutionTask(
        task_id=wire.task_id,
        task_kind=wire.task_kind,
        operation=wire.operation,
        profile_slot=ProfileSlot(wire.profile_slot),
        model_request=model_request,
        embedding_request=embedding_request,
        expires_at=wire.expires_at,
        lease={"memory_space_id": memory_space_id, "value": wire.lease},
        operation_input=wire.operation_input,
        structured_generation=wire.structured_generation,
    )


__all__ = [
    "CoreExecutionTaskWorker",
    "ExecutionFailureClassification",
    "classify_execution_error",
    "core_result_payload",
    "execution_result_is_retryable",
    "execution_task_from_wire",
]
