"""Generic Core task executor dispatching only on technical task kinds."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Literal, TypeVar, cast

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from ..embedding_purpose import EmbeddingPurpose
from .cancellation import CancellationToken
from .embedding_provider import (
    EmbeddingBatch,
    EmbeddingBatchRequest,
    EmbeddingProvider,
)
from .profile_slots import ProfileResolver, ProfileSlot
from .profiles import StructuredOutputMode
from .provider_telemetry import record_task
from .providers.base import ChatMessage, ProviderCancelledError, ProviderTimeoutError
from .structured_json_provider import StructuredJsonProvider

TaskKind = Literal["generate_json", "object_resolution", "embed_texts"]
ExecutionStatus = Literal[
    "completed", "failed", "unknown_task_kind", "cancelled", "timeout"
]

T = TypeVar("T")


class ModelRequestSpec(BaseModel):
    """Closed request spec for a generic generate_json task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    messages: tuple[ChatMessage, ...] = Field(min_length=1, max_length=32)
    max_output_tokens: int = Field(gt=0, le=50_000)
    response_format: dict[str, object] | None = None
    output_contract: dict[str, object] | None = None
    structured_output_requirement: dict[str, object] | None = None
    mode: StructuredOutputMode = Field(
        default="auto",
        validation_alias=AliasChoices("mode", "structured_output_mode"),
    )
    tool_name: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict[str, object] = Field(default_factory=dict)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)

    @property
    def structured_output_mode(self) -> StructuredOutputMode:
        return self.mode


class EmbeddingRequestSpec(BaseModel):
    """Closed request spec for a generic embed_texts task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    texts: tuple[str, ...] = Field(min_length=1)
    purpose: EmbeddingPurpose
    subject_refs: tuple[str, ...] | None = Field(default=None, max_length=512)
    dimensions: int | None = Field(default=None, gt=0, le=100_000)
    profile_fingerprint: str | None = Field(default=None, max_length=200)
    config_fingerprint: str | None = Field(default=None, max_length=200)
    privacy_class: str = Field(default="default", min_length=1, max_length=100)
    cache_namespace: str = Field(default="", max_length=200)
    cache_keys: tuple[str, ...] | None = Field(default=None, max_length=512)
    deadline: str | None = Field(default=None, max_length=64)
    role: Literal["query", "passage"] | None = None
    renderer_version: str | None = Field(default=None, min_length=1, max_length=200)


class GenericExecutionTask(BaseModel):
    """Technical task contract with no facet, value, or domain semantics.

    ``task_kind`` is left as an open string so the executor can defensively
    report unknown kinds instead of failing at construction time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1, max_length=200)
    task_kind: str = Field(min_length=1, max_length=200)
    operation: str | None = Field(default=None, max_length=200)
    profile_slot: ProfileSlot
    model_request: ModelRequestSpec | None = None
    embedding_request: EmbeddingRequestSpec | None = None
    expires_at: str | None = Field(default=None, max_length=64)
    lease: dict[str, object] | None = None
    operation_input: dict[str, object] | None = None
    structured_generation: dict[str, object] | None = None


class EgressAuditRecord(BaseModel):
    """Content-free egress statistics safe for logging and persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    task_kind: str = Field(min_length=1)
    profile_id: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=500)
    input_bytes: int = Field(ge=0)
    output_bytes: int = Field(ge=0)
    status: str = Field(min_length=1)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    usage_unknown: bool = True


class GenericExecutionResult(BaseModel):
    """Executor result with typed output and content-free egress audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    task_kind: str = Field(min_length=1)
    operation: str | None = Field(default=None, max_length=200)
    operation_input: dict[str, object] | None = None
    status: ExecutionStatus
    output: dict[str, object] | None = None
    embedding_result: EmbeddingBatch | None = None
    egress_audit: EgressAuditRecord
    error_code: str | None = Field(default=None, max_length=200)
    raw_model_text: str | None = None
    structured_output_mode: StructuredOutputMode | None = None
    contract_digest: str | None = Field(default=None, max_length=200)
    tool_name: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict[str, object] = Field(default_factory=dict)

    @property
    def mode(self) -> StructuredOutputMode | None:
        return self.structured_output_mode

    @property
    def selected_mode(self) -> StructuredOutputMode | None:
        return self.structured_output_mode


class CoreExecutorError(RuntimeError):
    """Base executor failure with a safe structured code."""

    code = "core_executor_error"


class ExecutionTimeoutError(CoreExecutorError):
    code = "timeout"

    def __init__(self, *args: object) -> None:
        del args
        super().__init__("task execution timed out")


class ExecutionCancelledError(CoreExecutorError):
    code = "cancelled"

    def __init__(self, *args: object) -> None:
        del args
        super().__init__("task execution cancelled")


class CoreTaskExecutor:
    """Dispatch generic tasks to providers by ``task_kind`` only.

    The ``operation`` field is intentionally never inspected: Local does not
    analyze operations. generate_json and embed_texts have separate timeouts,
    and cancellation flows through the shared CancellationToken.
    """

    def __init__(
        self,
        *,
        json_provider: StructuredJsonProvider,
        embedding_provider: EmbeddingProvider,
        profile_resolver: ProfileResolver,
        generate_json_timeout_seconds: float,
        embed_texts_timeout_seconds: float,
    ) -> None:
        self._json_provider = json_provider
        self._embedding_provider = embedding_provider
        self._profile_resolver = profile_resolver
        if generate_json_timeout_seconds <= 0:
            raise ValueError("generate_json_timeout_seconds must be positive")
        if embed_texts_timeout_seconds <= 0:
            raise ValueError("embed_texts_timeout_seconds must be positive")
        self.generate_json_timeout_seconds = float(generate_json_timeout_seconds)
        self.embed_texts_timeout_seconds = float(embed_texts_timeout_seconds)

    def execute(
        self,
        task: GenericExecutionTask,
        cancellation_token: CancellationToken | None = None,
        *,
        force_provider_fallback: bool = False,
    ) -> GenericExecutionResult:
        if task.task_kind in {"generate_json", "object_resolution"}:
            return self._execute_generate_json(
                task,
                cancellation_token,
                force_provider_fallback=force_provider_fallback,
            )
        if task.task_kind == "embed_texts":
            return self._execute_embed_texts(task, cancellation_token)
        return self._unknown_kind_result(task)

    def execute_batch(
        self,
        tasks: tuple[GenericExecutionTask, ...] | list[GenericExecutionTask],
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[GenericExecutionResult, ...]:
        """Execute a compatible task batch without interpreting its operation.

        Only the technical ``embed_texts`` shape is batched. Generation stays
        one task per call because its structured contract and output cannot be
        merged safely by Local.
        """

        normalized = tuple(tasks)
        if not normalized:
            return ()
        if all(task.task_kind == "embed_texts" for task in normalized):
            return self._execute_embed_texts_batch(normalized, cancellation_token)
        return tuple(self.execute(task, cancellation_token) for task in normalized)

    def _execute_generate_json(
        self,
        task: GenericExecutionTask,
        token: CancellationToken | None,
        *,
        force_provider_fallback: bool = False,
    ) -> GenericExecutionResult:
        spec = task.model_request
        if spec is None:
            return self._failed_result(
                task, error_code="invalid_request", input_bytes=0
            )
        input_bytes = _model_request_bytes(spec)
        telemetry_operation = _telemetry_operation(task)
        structured_metadata = task.structured_generation or {}
        attempt_kind = (
            str(structured_metadata.get("attempt_kind"))
            if isinstance(structured_metadata, dict)
            and structured_metadata.get("attempt_kind") is not None
            else "primary"
        )
        if attempt_kind == "empty_recheck":
            force_provider_fallback = True
        attempt_index = (
            structured_metadata.get("attempt_number")
            if isinstance(structured_metadata, dict)
            else None
        )
        root_task_id = (
            structured_metadata.get("root_task_id")
            if isinstance(structured_metadata, dict)
            else None
        )
        request_reason = (
            "semantic_repair"
            if attempt_kind in {"repair", "empty_recheck"}
            else ("agent_generation" if telemetry_operation == "agent_generation" else "primary")
        )
        record_task(
            kind="generation",
            operation=telemetry_operation,
            task_count=1,
            task_id=task.task_id,
            root_task_id=root_task_id or task.task_id,
            attempt_index=attempt_index if isinstance(attempt_index, int) else 0,
            request_reason=request_reason,
            structured_output_mode=spec.mode,
        )
        try:
            result = self._run_bounded(
                lambda: self._json_provider.generate_json(
                    memory_space_id=_memory_space_id(task),
                    messages=spec.messages,
                    max_output_tokens=spec.max_output_tokens,
                    output_contract=spec.output_contract,
                    structured_output_requirement=spec.structured_output_requirement,
                    mode=spec.mode,
                    tool_name=spec.tool_name,
                    metadata=spec.metadata,
                    telemetry_context={
                        "task_id": task.task_id,
                        "root_task_id": root_task_id or task.task_id,
                        "attempt_index": attempt_index if isinstance(attempt_index, int) else 0,
                        "request_reason": request_reason,
                        "attempt_kind": attempt_kind,
                    },
                    telemetry_operation=telemetry_operation,
                    seed=spec.seed,
                    force_provider_fallback=force_provider_fallback,
                    response_format=spec.response_format,
                    profile_slot=task.profile_slot,
                    cancellation_token=token,
                ),
                self.generate_json_timeout_seconds,
                token,
            )
        except Exception as exc:  # noqa: BLE001 - classify any provider failure
            return self._failure_result(
                task, exc, input_bytes=input_bytes, profile_id=_resolved_profile_id(exc)
            )
        audit = EgressAuditRecord(
            task_id=task.task_id,
            task_kind=task.task_kind,
            profile_id=result.profile_id,
            provider=result.provider,
            model=result.model,
            input_bytes=input_bytes,
            output_bytes=result.response_bytes,
            status="completed",
            input_tokens=_usage_int(result.normalized_usage, "input_tokens"),
            output_tokens=_usage_int(result.normalized_usage, "output_tokens"),
            total_tokens=_usage_int(result.normalized_usage, "total_tokens"),
            usage_unknown=bool(result.normalized_usage.get("usage_unknown", True)),
        )
        return GenericExecutionResult(
            task_id=task.task_id,
            task_kind=task.task_kind,
            operation=task.operation,
            operation_input=task.operation_input,
            status="completed",
            output=result.data,
            egress_audit=audit,
            raw_model_text=result.raw_text,
            structured_output_mode=result.structured_output_mode,
            contract_digest=result.contract_digest,
            tool_name=result.tool_name,
            metadata={
                **result.metadata,
                "parsed_json": result.parsed_json,
                "raw_text": result.raw_text,
                "provider_request_id": result.provider_request_id,
                "finish_reason": result.finish_reason,
                "transport_error": None,
            },
        )

    def _execute_embed_texts(
        self, task: GenericExecutionTask, token: CancellationToken | None
    ) -> GenericExecutionResult:
        spec = task.embedding_request
        if spec is None:
            return self._failed_result(
                task, error_code="invalid_request", input_bytes=0
            )
        input_bytes = sum(len(text.encode("utf-8")) for text in spec.texts)
        profile = None
        try:
            profile = self._profile_resolver.resolve_profile(
                _memory_space_id(task), task.profile_slot
            )
            batch = self._run_bounded(
                lambda: self._embedding_provider.embed_many(
                    (
                        EmbeddingBatchRequest(
                            texts=spec.texts,
                            profile=profile,
                            purpose=spec.purpose,
                            dimensions=spec.dimensions,
                            cache_keys=spec.cache_keys,
                            cache_namespace=(spec.cache_namespace or spec.privacy_class),
                            profile_fingerprint=spec.profile_fingerprint,
                            config_fingerprint=spec.config_fingerprint,
                            privacy_class=spec.privacy_class,
                            deadline=spec.deadline,
                            role=spec.role,
                            renderer_version=spec.renderer_version,
                        ),
                    ),
                    cancellation_token=token,
                ),
                self.embed_texts_timeout_seconds,
                token,
            )[0]
        except Exception as exc:  # noqa: BLE001 - classify any provider failure
            return self._failure_result(
                task,
                exc,
                input_bytes=input_bytes,
                profile_id=_resolved_profile_id(exc)
                or (profile.profile_id if profile is not None else None),
            )
        if spec.dimensions is not None and batch.dimensions != spec.dimensions:
            return self._failed_result(
                task,
                error_code="embedding_dimension_mismatch",
                input_bytes=input_bytes,
                profile_id=profile.profile_id,
            )
        audit = EgressAuditRecord(
            task_id=task.task_id,
            task_kind=task.task_kind,
            profile_id=profile.profile_id,
            provider="local",
            model=batch.model,
            input_bytes=input_bytes,
            output_bytes=_embedding_bytes(batch),
            status="completed",
            usage_unknown=True,
        )
        return GenericExecutionResult(
            task_id=task.task_id,
            task_kind=task.task_kind,
            operation=task.operation,
            operation_input=task.operation_input,
            status="completed",
            embedding_result=batch,
            egress_audit=audit,
        )

    def _execute_embed_texts_batch(
        self,
        tasks: tuple[GenericExecutionTask, ...],
        token: CancellationToken | None,
    ) -> tuple[GenericExecutionResult, ...]:
        specs = [task.embedding_request for task in tasks]
        if any(spec is None for spec in specs):
            return tuple(
                self._failed_result(task, error_code="invalid_request", input_bytes=0)
                for task in tasks
            )
        typed_specs = cast(list[EmbeddingRequestSpec], specs)
        profiles = []
        try:
            for task in tasks:
                profiles.append(
                    self._profile_resolver.resolve_profile(
                        _memory_space_id(task), task.profile_slot
                    )
                )
            first_profile = profiles[0]
            if any(
                (
                    profile.profile_id,
                    profile.model,
                    profile.base_url,
                    profile.provider_kind,
                    spec.profile_fingerprint,
                    spec.config_fingerprint,
                    spec.dimensions,
                    spec.privacy_class,
                    spec.cache_namespace,
                    spec.deadline,
                    spec.role,
                    spec.renderer_version,
                )
                != (
                    first_profile.profile_id,
                    first_profile.model,
                    first_profile.base_url,
                    first_profile.provider_kind,
                    typed_specs[0].profile_fingerprint,
                    typed_specs[0].config_fingerprint,
                    typed_specs[0].dimensions,
                    typed_specs[0].privacy_class,
                    typed_specs[0].cache_namespace,
                    typed_specs[0].deadline,
                    typed_specs[0].role,
                    typed_specs[0].renderer_version,
                )
                for profile, spec in zip(profiles[1:], typed_specs[1:], strict=True)
            ):
                return tuple(self.execute(task, token) for task in tasks)
            requests = tuple(
                EmbeddingBatchRequest(
                    texts=spec.texts,
                    profile=profile,
                    purpose=spec.purpose,
                    dimensions=spec.dimensions,
                    cache_keys=spec.cache_keys,
                    cache_namespace=(spec.cache_namespace or spec.privacy_class),
                    profile_fingerprint=spec.profile_fingerprint,
                    config_fingerprint=spec.config_fingerprint,
                    privacy_class=spec.privacy_class,
                    deadline=spec.deadline,
                    role=spec.role,
                    renderer_version=spec.renderer_version,
                )
                for spec, profile in zip(typed_specs, profiles, strict=True)
            )
            batches = self._run_bounded(
                lambda: self._embedding_provider.embed_many(
                    requests,
                    cancellation_token=token,
                ),
                self.embed_texts_timeout_seconds,
                token,
            )
            results: list[GenericExecutionResult] = []
            for task, spec, profile, batch in zip(
                tasks, typed_specs, profiles, batches, strict=True
            ):
                input_bytes = sum(len(text.encode("utf-8")) for text in spec.texts)
                if spec.dimensions is not None and batch.dimensions != spec.dimensions:
                    results.append(
                        self._failed_result(
                            task,
                            error_code="embedding_dimension_mismatch",
                            input_bytes=input_bytes,
                            profile_id=profile.profile_id,
                        )
                    )
                    continue
                results.append(
                    GenericExecutionResult(
                        task_id=task.task_id,
                        task_kind=task.task_kind,
                        operation=task.operation,
                        operation_input=task.operation_input,
                        status="completed",
                        embedding_result=batch,
                        egress_audit=EgressAuditRecord(
                            task_id=task.task_id,
                            task_kind=task.task_kind,
                            profile_id=profile.profile_id,
                            provider="local",
                            model=batch.model,
                            input_bytes=input_bytes,
                            output_bytes=_embedding_bytes(batch),
                            status="completed",
                            usage_unknown=True,
                        ),
                    )
                )
            return tuple(results)
        except Exception as exc:  # noqa: BLE001 - preserve one terminal result per task
            return tuple(
                self._failure_result(
                    task,
                    exc,
                    input_bytes=sum(len(text.encode("utf-8")) for text in spec.texts),
                    profile_id=(profile.profile_id if profile is not None else None),
                )
                for task, spec, profile in zip(tasks, typed_specs, profiles or [None] * len(tasks), strict=True)
            )

    def _run_bounded(
        self,
        work: Callable[[], T],
        timeout_seconds: float,
        token: CancellationToken | None,
    ) -> T:
        if token is None:
            token = CancellationToken()
        token.raise_if_cancelled()

        done = threading.Event()
        outcome: list[tuple[str, object]] = []

        def worker() -> None:
            try:
                outcome.append(("ok", work()))
            except BaseException as exc:  # noqa: BLE001 - relay worker failures
                outcome.append(("error", exc))
            finally:
                done.set()

        thread = threading.Thread(
            target=worker, daemon=True, name="ledgermind-core-executor"
        )
        thread.start()

        deadline = time.monotonic() + timeout_seconds
        cancelled = False
        timed_out = False
        while not done.is_set():
            if token.is_cancelled():
                cancelled = True
                done.wait(timeout=0.5)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                token.cancel()
                done.wait(timeout=0.5)
                break
            time.sleep(0.01)

        if cancelled:
            raise ExecutionCancelledError()
        if timed_out:
            raise ExecutionTimeoutError()
        if outcome:
            kind, value = outcome[0]
            if kind == "ok":
                return cast(T, value)
            raise cast(BaseException, value)
        raise ExecutionCancelledError()

    def _failure_result(
        self,
        task: GenericExecutionTask,
        exc: Exception,
        *,
        input_bytes: int,
        profile_id: str | None = None,
        provider: str | None = None,
    ) -> GenericExecutionResult:
        if isinstance(exc, (ExecutionTimeoutError, ProviderTimeoutError)):
            status: ExecutionStatus = "timeout"
            error_code = "timeout"
        elif isinstance(exc, (ExecutionCancelledError, ProviderCancelledError)):
            status = "cancelled"
            error_code = "cancelled"
        else:
            status = "failed"
            error_code = getattr(exc, "code", "execution_failed")
            if not isinstance(error_code, str) or not error_code:
                error_code = "execution_failed"
        return self._failed_result(
            task,
            error_code=error_code,
            input_bytes=input_bytes,
            profile_id=profile_id,
            provider=provider,
            status=status,
        )

    @staticmethod
    def _failed_result(
        task: GenericExecutionTask,
        *,
        error_code: str,
        input_bytes: int,
        profile_id: str | None = None,
        provider: str | None = None,
        status: ExecutionStatus = "failed",
    ) -> GenericExecutionResult:
        audit = EgressAuditRecord(
            task_id=task.task_id,
            task_kind=task.task_kind,
            profile_id=profile_id,
            provider=provider,
            model=None,
            input_bytes=input_bytes,
            output_bytes=0,
            status=status,
        )
        return GenericExecutionResult(
            task_id=task.task_id,
            task_kind=task.task_kind,
            operation=task.operation,
            operation_input=task.operation_input,
            status=status,
            egress_audit=audit,
            error_code=error_code,
            metadata={"error_category": _error_category(error_code)},
        )

    @staticmethod
    def _unknown_kind_result(task: GenericExecutionTask) -> GenericExecutionResult:
        return CoreTaskExecutor._failed_result(
            task,
            error_code="unknown_task_kind",
            input_bytes=0,
            status="unknown_task_kind",
        )


def _memory_space_id(task: GenericExecutionTask) -> str:
    value = task.lease.get("memory_space_id") if task.lease else None
    return value if isinstance(value, str) else ""


def _telemetry_operation(task: GenericExecutionTask) -> object:
    """Expose structured repair work separately from its parent operation."""

    structured = task.structured_generation
    if isinstance(structured, dict) and structured.get("attempt_kind") in {
        "repair",
        "empty_recheck",
    }:
        return "semantic_repair"
    return task.operation


def _error_category(error_code: str) -> str:
    if error_code in {
        "provider_timeout",
        "provider_transport_error",
        "provider_unavailable",
        "transport_error",
        "transient_provider_error",
        "timeout",
    }:
        return "transport_failure"
    if error_code in {"invalid_json_response", "invalid_provider_response"}:
        return "json_parse_failure"
    if error_code == "length_truncation":
        return "json_parse_failure"
    if error_code in {"invalid_model_output", "schema_shape_failure"}:
        return "schema_shape_failure"
    if error_code in {
        "semantic_validation_failure",
        "semantic_output_invalid",
        "semantic_repair_rejected",
    }:
        return "semantic_validation_failure"
    if error_code in {"language_fidelity_failure", "language_mismatch"}:
        return "language_fidelity_failure"
    if error_code in {
        "grounding_failure",
        "claim_grounding_failure",
        "unknown_anchor_ref",
        "unknown_candidate_id",
    }:
        return "grounding_failure"
    if error_code in {
        "authentication_error",
        "configuration_error",
        "provider_capability_unverified",
        "secret_missing",
    }:
        return "transport_failure"
    return "transport_failure" if error_code.startswith("provider_") else "schema_shape_failure"


def _model_request_bytes(spec: ModelRequestSpec) -> int:
    payload: dict[str, object] = {
        "messages": [
            {"role": message.role, "content": message.content}
            for message in spec.messages
        ],
        "max_output_tokens": spec.max_output_tokens,
        "output_contract": spec.output_contract,
        "mode": spec.mode,
        "tool_name": spec.tool_name,
    }
    return len(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _embedding_bytes(batch: EmbeddingBatch) -> int:
    return len(batch.vectors) * batch.dimensions * 4


def _resolved_profile_id(exc: Exception) -> str | None:
    profile_id = getattr(exc, "profile_id", None)
    if isinstance(profile_id, str) and profile_id:
        return profile_id
    return None


def _usage_int(usage: dict[str, object], key: str) -> int | None:
    value = usage.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


__all__ = [
    "CoreExecutorError",
    "CoreTaskExecutor",
    "EgressAuditRecord",
    "EmbeddingBatchRequest",
    "EmbeddingPurpose",
    "EmbeddingRequestSpec",
    "ExecutionCancelledError",
    "ExecutionStatus",
    "ExecutionTimeoutError",
    "GenericExecutionResult",
    "GenericExecutionTask",
    "ModelRequestSpec",
    "TaskKind",
]
