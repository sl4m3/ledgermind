"""Generic Core task executor dispatching only on technical task kinds."""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from collections.abc import Callable
from typing import Any, Literal, TypeVar, cast

import httpx

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

TaskKind = Literal["generate_json", "object_resolution", "embed_texts", "decide"]
ExecutionStatus = Literal["completed", "failed", "unknown_task_kind", "cancelled", "timeout"]

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
    decision_request: dict[str, object] | None = None
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


def _normalize_packaging_output(output: Any) -> Any:
    if not isinstance(output, dict) or "o" not in output:
        return output
    cards = output.get("o")
    if not isinstance(cards, list):
        return output
    changed = False
    new_cards = []
    for card in cards:
        if not isinstance(card, dict) or "c" not in card:
            new_cards.append(card)
            continue
        claims = card.get("c")
        if not isinstance(claims, list):
            new_cards.append(card)
            continue
        new_claims = []
        for claim in claims:
            if isinstance(claim, dict):
                copy = claim.get("copy")
                if isinstance(copy, list) and len(copy) > 1 and "b" not in claim and "f" in claim:
                    new_claim = dict(claim)
                    del new_claim["copy"]
                    new_claim["b"] = [{"copy": copy}]
                    if "k" not in new_claim:
                        new_claim["k"] = []
                    new_claims.append(new_claim)
                    changed = True
                    continue
            new_claims.append(claim)
        new_card = dict(card)
        new_card["c"] = new_claims
        new_cards.append(new_card)
    if not changed:
        return output
    new_output = dict(output)
    new_output["o"] = new_cards
    return new_output


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
        generation_concurrency: int = 1,
        batch_cache_path: str | Path | None = None,
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
        self.generation_concurrency = int(generation_concurrency)
        self._batch_cache_path = Path(batch_cache_path) if batch_cache_path is not None else None
        self._batch_cache: dict[str, Any] | None = None
        self._batch_cache_mtime: float = 0.0

    def execute(
        self,
        task: GenericExecutionTask,
        cancellation_token: CancellationToken | None = None,
        *,
        force_provider_fallback: bool = False,
    ) -> GenericExecutionResult:
        if task.task_kind in {"generate_json", "object_resolution", "decide"}:
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

    def _lookup_batch_cache(self, task: GenericExecutionTask) -> dict[str, Any] | None:
        """Lookup precomputed batch outputs for deterministic stage execution."""
        cache_file = self._batch_cache_path
        if cache_file is None:
            env_path = os.environ.get("LEDGERMIND_BATCH_CACHE_PATH")
            if env_path:
                cache_file = Path(env_path)

        if cache_file is not None and cache_file.is_file():
            try:
                mtime = cache_file.stat().st_mtime
                if self._batch_cache is None or mtime > self._batch_cache_mtime:
                    self._batch_cache = json.loads(cache_file.read_text(encoding="utf-8"))
                    self._batch_cache_mtime = mtime
            except Exception:
                if self._batch_cache is None:
                    self._batch_cache = {}
        elif self._batch_cache is None:
            self._batch_cache = {}

        if not self._batch_cache:
            return None

        # 1. Direct task ID match
        if task.task_id in self._batch_cache:
            return self._batch_cache[task.task_id]

        op_input = task.operation_input or {}
        raw_round = op_input.get("raw_round") or {}
        source = raw_round.get("source") if isinstance(raw_round, dict) else None
        source_round_id = source.get("round_id") if isinstance(source, dict) else None

        round_identifiers = [
            source_round_id,
            op_input.get("round_id"),
            op_input.get("raw_round_id"),
            task.task_id,
        ]

        stage = (op_input.get("round_memory") or {}).get("stage")
        contract = (
            (task.model_request.output_contract or {}).get("contract_name")
            if task.model_request
            else None
        )

        stage_variants = []
        if stage:
            stage_variants.append(stage)
        if contract:
            stage_variants.append(contract)
            if contract.startswith("operational_round_memory_"):
                suffix = contract.removeprefix("operational_round_memory_")
                if suffix not in stage_variants:
                    stage_variants.append(suffix)
            elif contract.startswith("round_memory_"):
                suffix = contract.removeprefix("round_memory_")
                if suffix not in stage_variants:
                    stage_variants.append(suffix)

        for rid in round_identifiers:
            if not rid or not isinstance(rid, str):
                continue
            if rid in self._batch_cache:
                return self._batch_cache[rid]
            for svar in stage_variants:
                for sep in (":", "__", "-"):
                    key = f"{rid}{sep}{svar}"
                    if key in self._batch_cache:
                        return self._batch_cache[key]

        return None

    def _execute_generate_json(
        self,
        task: GenericExecutionTask,
        token: CancellationToken | None,
        *,
        force_provider_fallback: bool = False,
    ) -> GenericExecutionResult:
        spec = task.model_request
        if spec is None:
            return self._failed_result(task, error_code="invalid_request", input_bytes=0)
        input_bytes = _model_request_bytes(spec)
        precomputed = (task.operation_input or {}).get("core_precomputed_output")
        if precomputed is not None:
            # Opaque Core-authored durable projection, not a Local semantic
            # decision. Core verifies it against the original offered graph.
            if token is not None:
                token.raise_if_cancelled()
            return GenericExecutionResult(
                task_id=task.task_id,
                task_kind=task.task_kind,
                operation=task.operation,
                operation_input=task.operation_input,
                status="completed",
                output=precomputed,
                structured_output_mode=spec.mode,
                contract_digest=(spec.output_contract or {}).get("schema_digest"),
                metadata={
                    "core_precomputed_result": True,
                    "model_calls": 0,
                    "cost_status": "not_applicable_no_http",
                },
                egress_audit=EgressAuditRecord(
                    task_id=task.task_id,
                    task_kind=task.task_kind,
                    profile_id="core-projection",
                    provider="Core",
                    model="not-inferred",
                    input_bytes=0,
                    output_bytes=len(json.dumps(precomputed, ensure_ascii=False).encode()),
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    usage_unknown=False,
                    status="completed",
                ),
            )
        cached_entry = self._lookup_batch_cache(task)
        if cached_entry is not None and cached_entry.get("status") == "completed":
            if token is not None:
                token.raise_if_cancelled()
            cached_output = _normalize_packaging_output(cached_entry["output"])
            usage = cached_entry.get("usage", {})
            return GenericExecutionResult(
                task_id=task.task_id,
                task_kind=task.task_kind,
                operation=task.operation,
                operation_input=task.operation_input,
                status="completed",
                output=cached_output,
                structured_output_mode=spec.mode,
                contract_digest=(spec.output_contract or {}).get("schema_digest"),
                metadata={
                    "batch_cached_result": True,
                    "model_calls": 1,
                    "batch_id": cached_entry.get("batch_id"),
                    "cost_status": "batch_reported",
                },
                egress_audit=EgressAuditRecord(
                    task_id=task.task_id,
                    task_kind=task.task_kind,
                    profile_id="haiku-batch",
                    provider="anthropic",
                    model="anthropic/claude-haiku-5.5:batch",
                    input_bytes=input_bytes,
                    output_bytes=len(json.dumps(cached_output, ensure_ascii=False).encode()),
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    usage_unknown=False,
                    status="completed",
                ),
            )
        is_round_memory = (
            (task.operation_input and task.operation_input.get("round_memory") is not None)
            or (
                isinstance(task.operation, str)
                and (
                    task.operation.startswith("operational_round_memory_")
                    or task.operation.startswith("round_memory_")
                )
            )
        )
        if is_round_memory:
            raise RuntimeError(
                f"Batch execution required: task '{task.task_id}' (operation='{task.operation}', "
                f"round='{(task.operation_input or {}).get('raw_round_id')}') was not found in "
                "batch cache. Streaming model fallback is strictly prohibited."
            )
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
            structured_metadata.get("chain_root_task_id") or structured_metadata.get("root_task_id")
            if isinstance(structured_metadata, dict)
            else None
        )
        request_reason = (
            "semantic_repair"
            if attempt_kind in {"repair", "empty_recheck"}
            else ("agent_generation" if telemetry_operation == "agent_generation" else "primary")
        )
        record_task(
            kind="decision" if task.task_kind == "decide" else "generation",
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
                lambda: (
                    self._json_provider.decide
                    if task.task_kind == "decide"
                    else self._json_provider.generate_json
                )(
                    **(
                        {
                            "decision_request": task.decision_request,
                            **(
                                {
                                    "decision_metadata_view": (task.operation_input or {})[
                                        "decision_metadata_view"
                                    ],
                                    "decision_metadata_pipeline": (task.operation_input or {}).get(
                                        "resolution_pipeline"
                                    ),
                                    "decision_metadata_operation": task.operation,
                                }
                                if "decision_metadata_view" in (task.operation_input or {})
                                else {}
                            ),
                            **(
                                {
                                    "native_batch_plan": (task.operation_input or {})[
                                        "native_kr_batch_plan"
                                    ],
                                    "native_batch_full_request": (task.operation_input or {}).get(
                                        "full_decision_request"
                                    ),
                                    "native_batch_index": (task.operation_input or {}).get(
                                        "decision_batch_index"
                                    ),
                                    "native_batch_pipeline": (task.operation_input or {}).get(
                                        "resolution_pipeline"
                                    ),
                                    "native_batch_operation": task.operation,
                                }
                                if "native_kr_batch_plan" in (task.operation_input or {})
                                else {}
                            ),
                        }
                        if task.task_kind == "decide"
                        else {}
                    ),
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
                        "resolution_pipeline": (task.operation_input or {}).get(
                            "resolution_pipeline"
                        ),
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
            input_bytes=(
                result.request_bytes
                if task.task_kind == "decide"
                and (
                    "decision_metadata_view" in (task.operation_input or {})
                    or "native_kr_batch_plan" in (task.operation_input or {})
                )
                else input_bytes
            ),
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
                "decision_task_id": (task.operation_input or {}).get("decision_task_id"),
                "decision_question_version": (task.operation_input or {}).get(
                    "decision_question_version"
                ),
                "resolution_stage": (task.operation_input or {}).get("resolution_stage"),
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
            return self._failed_result(task, error_code="invalid_request", input_bytes=0)
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
                for task, spec, profile in zip(
                    tasks, typed_specs, profiles or [None] * len(tasks), strict=True
                )
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

        thread = threading.Thread(target=worker, daemon=True, name="ledgermind-core-executor")
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
        import traceback
        print(f"[CoreTaskExecutor ERROR] task={task.task_id} kind={task.task_kind} op={task.operation} exc={exc!r}", flush=True)
        traceback.print_exc()
        if isinstance(exc, (ExecutionTimeoutError, ProviderTimeoutError, TimeoutError)):
            status: ExecutionStatus = "timeout"
            error_code = "timeout"
        elif isinstance(exc, (ExecutionCancelledError, ProviderCancelledError)):
            status = "cancelled"
            error_code = "cancelled"
        else:
            status = "failed"
            code = getattr(exc, "code", None)
            if isinstance(code, str) and code:
                error_code = code
            elif isinstance(exc, (OSError, ConnectionError)):
                error_code = "provider_transport_error"
            elif isinstance(exc, (MemoryError, RuntimeError)):
                error_code = "provider_executor_unclassified"
            elif isinstance(exc, httpx.TimeoutException):
                error_code = "timeout"
            elif isinstance(exc, (httpx.RequestError, httpx.TransportError)):
                error_code = "provider_transport_error"
            else:
                error_code = "execution_failed"
        return self._failed_result(
            task,
            error_code=error_code,
            input_bytes=input_bytes,
            profile_id=profile_id,
            provider=provider,
            status=status,
            exc=exc,
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
        exc: Exception | None = None,
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
        metadata: dict[str, Any] = {"error_category": _error_category(error_code)}
        if exc is not None:
            metadata["error_type"] = type(exc).__name__
            metadata["error_message"] = str(exc)
            import traceback

            metadata["error_traceback"] = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
        return GenericExecutionResult(
            task_id=task.task_id,
            task_kind=task.task_kind,
            operation=task.operation,
            operation_input=task.operation_input,
            status=status,
            egress_audit=audit,
            error_code=error_code,
            metadata=metadata,
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
    if task.task_kind == "decide":
        return f"{task.operation}_decision"
    memory = (task.operation_input or {}).get("round_memory")
    if isinstance(memory, dict) and memory.get("version") in {
        "round_memory_two_stage_v1",
        "round_memory_two_stage_v2",
        "round_memory_two_stage_v3",
        "round_memory_two_stage_v4",
        "round_memory_two_stage_v5",
        "addressed_write_v1",
        "memory_write_v1",
        "memory_write_v2",
        "memory_write_v3",
        "memory_write_v4",
        "memory_write_v5",
        "memory_write_v6",
        "memory_write_v7",
        "memory_write_v8",
    }:
        stage = memory.get("stage")
        if stage in {"preparation", "packaging"}:
            return f"round_memory_{stage}"
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
    if error_code in {"provider_executor_unclassified", "execution_failed"}:
        return "executor_failure"
    return "transport_failure" if error_code.startswith("provider_") else "schema_shape_failure"


def _model_request_bytes(spec: ModelRequestSpec) -> int:
    payload: dict[str, object] = {
        "messages": [
            {"role": message.role, "content": message.content} for message in spec.messages
        ],
        "max_output_tokens": spec.max_output_tokens,
        "output_contract": spec.output_contract,
        "mode": spec.mode,
        "tool_name": spec.tool_name,
    }
    return len(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
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
