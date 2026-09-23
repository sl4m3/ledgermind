"""Stable Local-to-Core command contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from ..embedding_purpose import validate_embedding_purpose
from ..inference.strict import STRICT_JSON_SCHEMA_MODE, validate_strict_requirement


class CoreGatewayError(RuntimeError):
    """Base error for Core delivery failures."""


class TransientCoreError(CoreGatewayError):
    """Core is temporarily unavailable and the command may be retried."""


class CoreCapabilityError(CoreGatewayError):
    """The connected Core did not advertise a required IPC capability."""

    def __init__(
        self,
        *,
        requested: tuple[str, ...],
        missing_operations: tuple[str, ...] = (),
        missing_capabilities: tuple[str, ...] = (),
        expected_schema_version: int | None = None,
        advertised_schema_version: int | None = None,
        reason_code: str = "core_capability_missing",
        expected_protocol_version: int | None = None,
        advertised_protocol_version: int | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.code = reason_code
        self.requested = requested
        self.missing_operations = missing_operations
        self.missing_capabilities = missing_capabilities
        self.expected_schema_version = expected_schema_version
        self.advertised_schema_version = advertised_schema_version
        self.expected_protocol_version = expected_protocol_version
        self.advertised_protocol_version = advertised_protocol_version
        details: list[str] = []
        if missing_operations:
            details.append("operations=" + ",".join(missing_operations))
        if missing_capabilities:
            details.append("capabilities=" + ",".join(missing_capabilities))
        if expected_schema_version is not None:
            details.append(
                "schema="
                + f"{advertised_schema_version or 'unavailable'}"
                + f" (required {expected_schema_version})"
            )
        if expected_protocol_version is not None:
            details.append(
                "protocol="
                + f"{advertised_protocol_version or 'unavailable'}"
                + f" (required {expected_protocol_version})"
            )
        suffix = "; ".join(details) if details else "no advertised support"
        super().__init__(f"Core capability validation failed: {suffix}")


class DomainRejectedError(CoreGatewayError):
    """Core rejected a validly delivered command for a domain reason."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _required(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def _timestamp(value: object, name: str) -> str:
    text = _required(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return text


def _strict_mapping(payload: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {sorted(unknown)}")


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class IngestRawRoundCommand:
    """RawRound delivery envelope; the payload is loaded by the worker."""

    command_id: str
    idempotency_key: str
    memory_space_id: str
    raw_round_id: str
    raw_round: dict[str, Any]
    resolution_context: dict[str, Any] | None = None
    embedding_profile: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.embedding_profile is not None and not isinstance(
            self.embedding_profile, dict
        ):
            raise TypeError("embedding_profile must be an object")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "memory_space_id": self.memory_space_id,
            "raw_round_id": self.raw_round_id,
            "raw_round": self.raw_round,
        }
        if self.resolution_context is not None:
            payload["resolution_context"] = self.resolution_context
        if self.embedding_profile is not None:
            payload["embedding_profile"] = self.embedding_profile
        return payload


@dataclass(frozen=True, slots=True)
class IngestRawRoundResult:
    accepted: bool
    duplicate: bool
    core_raw_round_id: str | None = None
    result_json: str | None = None


@dataclass(frozen=True, slots=True)
class CoreExecutionTask:
    """Strict technical execution envelope owned by the Local boundary.

    ``operation`` and ``operation_input`` are deliberately opaque.  Local only
    dispatches on ``task_kind`` and the Core remains the owner of domain
    semantics such as extraction and consolidation.
    """

    schema_version: int
    task_id: str
    task_kind: Literal["generate_json", "object_resolution", "embed_texts"]
    operation: str
    profile_slot: Literal["operational", "object_resolution", "background", "embedding"]
    memory_space_id: str
    expires_at: str
    lease: str | None
    model_request: dict[str, Any] | None
    embedding_request: dict[str, Any] | None
    operation_input: dict[str, Any] | None
    structured_generation: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("schema_version must be 2")
        _required(self.task_id, "task_id")
        _required(self.operation, "operation")
        _required(self.memory_space_id, "memory_space_id")
        _timestamp(self.expires_at, "expires_at")
        if self.lease is not None:
            _timestamp(self.lease, "lease")
        for value, name in (
            (self.model_request, "model_request"),
            (self.embedding_request, "embedding_request"),
            (self.operation_input, "operation_input"),
            (self.structured_generation, "structured_generation"),
        ):
            if value is not None and not isinstance(value, dict):
                raise TypeError(f"{name} must be an object")
        if self.task_kind not in {"generate_json", "object_resolution", "embed_texts"}:
            raise ValueError(
                "task_kind must be generate_json, object_resolution, or embed_texts"
            )
        if self.task_kind in {"generate_json", "object_resolution"}:
            if self.profile_slot not in {
                "operational",
                "object_resolution",
                "background",
            }:
                raise ValueError(
                    "generate_json task requires an operational, object_resolution, or background profile slot"
                )
            if self.model_request is None or self.embedding_request is not None:
                raise ValueError("generate_json task has an invalid request shape")
            _strict_mapping(
                self.model_request,
                {
                    "messages",
                    "max_output_tokens",
                    "response_format",
                    "output_contract",
                    "structured_output_requirement",
                    "mode",
                    "structured_output_mode",
                    "tool_name",
                    "metadata",
                    "seed",
                },
                "model_request",
            )
            messages = self.model_request.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError("model_request.messages must be a non-empty array")
            max_output_tokens = self.model_request.get("max_output_tokens")
            if (
                isinstance(max_output_tokens, bool)
                or not isinstance(max_output_tokens, int)
                or not 1 <= max_output_tokens <= 50_000
            ):
                raise TypeError("model_request.max_output_tokens must be an integer")
            response_format = self.model_request.get("response_format")
            if response_format is not None:
                if isinstance(response_format, str):
                    valid_response_format = response_format in {
                        "json_object",
                        "text",
                    }
                elif isinstance(response_format, dict):
                    valid_response_format = response_format.get("type") in {
                        "json_object",
                        "json_schema",
                    }
                else:
                    valid_response_format = False
                if not valid_response_format:
                    raise ValueError("model_request.response_format is invalid")
            output_contract = self.model_request.get("output_contract")
            if output_contract is not None and not isinstance(output_contract, dict):
                raise TypeError("model_request.output_contract must be an object")
            structured_output_requirement = self.model_request.get(
                "structured_output_requirement"
            )
            if structured_output_requirement is not None and not isinstance(
                structured_output_requirement, dict
            ):
                raise TypeError(
                    "model_request.structured_output_requirement must be an object"
                )
            if response_format is None and output_contract is None:
                raise ValueError(
                    "model_request requires output_contract or response_format"
                )
            mode = self.model_request.get(
                "mode", self.model_request.get("structured_output_mode")
            )
            if mode is not None and mode not in {
                "auto",
                "strict_json_schema",
                "json_schema",
                "tool_call",
                "json_object",
                "prompt_only",
            }:
                raise ValueError("model_request mode is invalid")
            if self.operation in {
                "round_semantic",
                "user_semantic",
                "execution_semantic",
                "object_resolution",
            }:
                if mode != STRICT_JSON_SCHEMA_MODE:
                    raise ValueError(
                        "semantic generate_json tasks require mode=strict_json_schema"
                    )
                try:
                    validate_strict_requirement(
                        structured_output_requirement,
                        output_contract,
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "semantic generate_json task has an invalid strict requirement"
                    ) from exc
                structured_generation = self.structured_generation or {}
                contract_digest = structured_generation.get("contract_digest")
                output_digest = (
                    output_contract.get("schema_digest")
                    if isinstance(output_contract, dict)
                    else None
                )
                if (
                    not isinstance(contract_digest, str)
                    or contract_digest != output_digest
                ):
                    raise ValueError(
                        "semantic task contract digest must match the strict output contract"
                    )
            tool_name = self.model_request.get("tool_name")
            if tool_name is not None:
                _required(tool_name, "model_request.tool_name")
            metadata = self.model_request.get("metadata")
            if metadata is not None and not isinstance(metadata, dict):
                raise TypeError("model_request.metadata must be an object")
            seed = self.model_request.get("seed")
            if seed is not None and (
                isinstance(seed, bool) or not isinstance(seed, int) or seed < 0
            ):
                raise TypeError("model_request.seed must be a non-negative integer")
            for message in messages:
                if not isinstance(message, dict):
                    raise TypeError("model_request.messages must contain objects")
                _strict_mapping(message, {"role", "content"}, "model message")
                _required(message.get("role"), "model message role")
                _required(message.get("content"), "model message content")
        else:
            if self.profile_slot != "embedding":
                raise ValueError("embed_texts task requires the embedding profile slot")
            if self.embedding_request is None or self.model_request is not None:
                raise ValueError("embed_texts task has an invalid request shape")
            _strict_mapping(
                self.embedding_request,
                {
                    "texts",
                    "purpose",
                    "subject_refs",
                    "dimensions",
                    "profile_fingerprint",
                    "config_fingerprint",
                    "privacy_class",
                    "cache_namespace",
                    "cache_keys",
                    "deadline",
                    "role",
                    "renderer_version",
                },
                "embedding_request",
            )
            texts = self.embedding_request.get("texts")
            if not isinstance(texts, list) or not texts:
                raise ValueError("embedding_request.texts must be a non-empty array")
            if any(not isinstance(text, str) or not text.strip() for text in texts):
                raise ValueError("embedding_request.texts must contain text")
            subject_refs = self.embedding_request.get("subject_refs")
            if subject_refs is not None:
                if not isinstance(subject_refs, list) or any(
                    not isinstance(subject_ref, str) or not subject_ref.strip()
                    for subject_ref in subject_refs
                ):
                    raise ValueError(
                        "embedding_request.subject_refs must contain strings"
                    )
                if len(set(subject_refs)) != len(subject_refs):
                    raise ValueError("embedding_request.subject_refs must be unique")
            purpose = validate_embedding_purpose(
                _required(self.embedding_request.get("purpose"), "embedding purpose")
            )
            role = self.embedding_request.get("role")
            if role is not None and role not in {"query", "passage"}:
                raise ValueError("embedding_request.role must be query or passage")
            required_role = {
                "object_candidate_query": "query",
                "object_identity_passage": "passage",
            }.get(purpose)
            if required_role is not None and role != required_role:
                raise ValueError(
                    f"embedding_request purpose {purpose} requires role={required_role}"
                )
            dimensions = self.embedding_request.get("dimensions")
            if dimensions is not None and (
                isinstance(dimensions, bool)
                or not isinstance(dimensions, int)
                or not 1 <= dimensions <= 100_000
            ):
                raise TypeError(
                    "embedding_request.dimensions must be a positive integer"
                )
            for key in (
                "profile_fingerprint",
                "config_fingerprint",
                "privacy_class",
                "cache_namespace",
                "deadline",
                "renderer_version",
            ):
                value = self.embedding_request.get(key)
                if value is not None and (
                    not isinstance(value, str) or not value.strip()
                ):
                    raise ValueError(f"embedding_request.{key} must be non-empty text")
            cache_keys = self.embedding_request.get("cache_keys")
            if cache_keys is not None:
                if not isinstance(cache_keys, list) or len(cache_keys) != len(texts):
                    raise ValueError(
                        "embedding_request.cache_keys must align with texts"
                    )
                if any(
                    not isinstance(key, str) or not key.strip() for key in cache_keys
                ):
                    raise ValueError(
                        "embedding_request.cache_keys must contain strings"
                    )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> CoreExecutionTask:
        _strict_mapping(
            payload,
            {
                "schema_version",
                "task_id",
                "task_kind",
                "operation",
                "profile_slot",
                "memory_space_id",
                "expires_at",
                "lease",
                "model_request",
                "embedding_request",
                "operation_input",
                "structured_generation",
            },
            "object-facet execution task",
        )
        task_kind = payload.get("task_kind")
        if task_kind not in {"generate_json", "object_resolution", "embed_texts"}:
            raise ValueError(
                "task_kind must be generate_json, object_resolution, or embed_texts"
            )
        profile_slot = payload.get("profile_slot")
        if profile_slot not in {
            "operational",
            "object_resolution",
            "background",
            "embedding",
        }:
            raise ValueError("profile_slot is invalid")
        model_request = payload.get("model_request")
        embedding_request = payload.get("embedding_request")
        operation_input = payload.get("operation_input")
        for value, name in (
            (model_request, "model_request"),
            (embedding_request, "embedding_request"),
            (operation_input, "operation_input"),
            (payload.get("structured_generation"), "structured_generation"),
        ):
            if value is not None and not isinstance(value, dict):
                raise TypeError(f"{name} must be an object")
        return cls(
            schema_version=_non_negative_int(
                payload.get("schema_version"), "schema_version"
            ),
            task_id=_required(payload.get("task_id"), "task_id"),
            task_kind=task_kind,
            operation=_required(payload.get("operation"), "operation"),
            profile_slot=profile_slot,
            memory_space_id=_required(
                payload.get("memory_space_id"), "memory_space_id"
            ),
            expires_at=_required(payload.get("expires_at"), "expires_at"),
            lease=(
                _required(payload["lease"], "lease")
                if payload.get("lease") is not None
                else None
            ),
            model_request=dict(model_request) if model_request is not None else None,
            embedding_request=(
                dict(embedding_request) if embedding_request is not None else None
            ),
            operation_input=(
                dict(operation_input) if operation_input is not None else None
            ),
            structured_generation=(
                dict(payload["structured_generation"])
                if isinstance(payload.get("structured_generation"), dict)
                else None
            ),
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "task_kind": self.task_kind,
            "operation": self.operation,
            "profile_slot": self.profile_slot,
            "memory_space_id": self.memory_space_id,
            "expires_at": self.expires_at,
            "model_request": self.model_request,
            "embedding_request": self.embedding_request,
            "operation_input": self.operation_input,
        }
        if self.structured_generation is not None:
            payload["structured_generation"] = self.structured_generation
        if self.lease is not None:
            payload["lease"] = self.lease
        return payload


@dataclass(frozen=True, slots=True)
class CoreExecutionResult:
    """Strict generic result envelope sent back to Core."""

    task_id: str
    task_kind: Literal["generate_json", "object_resolution", "embed_texts"]
    status: Literal["completed"]
    operation: str
    operation_input: dict[str, Any] | None
    output: dict[str, Any] | None
    embedding_result: dict[str, Any] | None
    egress_audit: dict[str, Any]
    error_code: str | None = None
    raw_model_text: str | None = None
    structured_output_mode: str | None = None
    contract_digest: str | None = None
    tool_name: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _required(self.task_id, "result.task_id")
        _required(self.operation, "result.operation")
        if self.task_kind not in {"generate_json", "object_resolution", "embed_texts"}:
            raise ValueError("result.task_kind is invalid")
        if self.status != "completed":
            raise ValueError("result.status must be completed")
        if self.operation_input is not None and not isinstance(
            self.operation_input, dict
        ):
            raise TypeError("result.operation_input must be an object")
        if self.output is not None and not isinstance(self.output, dict):
            raise TypeError("result.output must be an object")
        if self.embedding_result is not None and not isinstance(
            self.embedding_result, dict
        ):
            raise TypeError("result.embedding_result must be an object")
        if not isinstance(self.egress_audit, dict):
            raise TypeError("result.egress_audit must be an object")
        if self.task_kind in {"generate_json", "object_resolution"}:
            if self.output is None or self.embedding_result is not None:
                raise ValueError("generate_json result has an invalid output shape")
        elif self.embedding_result is None or self.output is not None:
            raise ValueError("embed_texts result has an invalid output shape")
        if self.error_code is not None:
            _required(self.error_code, "result.error_code")
        if self.raw_model_text is not None and not isinstance(self.raw_model_text, str):
            raise TypeError("result.raw_model_text must be a string")
        if self.structured_output_mode is not None:
            _required(self.structured_output_mode, "result.structured_output_mode")
        if self.contract_digest is not None:
            _required(self.contract_digest, "result.contract_digest")
        if self.tool_name is not None:
            _required(self.tool_name, "result.tool_name")
        if self.metadata is not None and not isinstance(self.metadata, dict):
            raise TypeError("result.metadata must be an object")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "task_id": self.task_id,
            "task_kind": self.task_kind,
            "status": self.status,
            "operation": self.operation,
            "operation_input": self.operation_input,
            "output": self.output,
            "embedding_result": self.embedding_result,
            "egress_audit": self.egress_audit,
            "error_code": self.error_code,
        }
        if self.raw_model_text is not None:
            payload["raw_model_text"] = self.raw_model_text
        if self.structured_output_mode is not None:
            payload["structured_output_mode"] = self.structured_output_mode
        if self.contract_digest is not None:
            payload["contract_digest"] = self.contract_digest
        if self.tool_name is not None:
            payload["tool_name"] = self.tool_name
        if self.metadata is not None:
            payload["metadata"] = self.metadata
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> CoreExecutionResult:
        _strict_mapping(
            payload,
            {
                "task_id",
                "task_kind",
                "status",
                "operation",
                "operation_input",
                "output",
                "embedding_result",
                "egress_audit",
                "error_code",
                "raw_model_text",
                "structured_output_mode",
                "contract_digest",
                "tool_name",
                "metadata",
            },
            "object-facet execution result",
        )
        task_kind = payload.get("task_kind")
        if task_kind not in {"generate_json", "object_resolution", "embed_texts"}:
            raise ValueError("result.task_kind is invalid")
        if payload.get("status") != "completed":
            raise ValueError("result.status must be completed")
        operation_input = payload.get("operation_input")
        output = payload.get("output")
        embedding_result = payload.get("embedding_result")
        audit = payload.get("egress_audit")
        for value, name in (
            (operation_input, "result.operation_input"),
            (output, "result.output"),
            (embedding_result, "result.embedding_result"),
            (audit, "result.egress_audit"),
        ):
            if value is not None and not isinstance(value, dict):
                raise TypeError(f"{name} must be an object")
        if not isinstance(audit, dict):
            raise TypeError("result.egress_audit must be an object")
        raw_model_text = payload.get("raw_model_text")
        if raw_model_text is not None and not isinstance(raw_model_text, str):
            raise TypeError("result.raw_model_text must be a string")
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("result.metadata must be an object")
        if task_kind in {"generate_json", "object_resolution"}:
            if not isinstance(output, dict) or embedding_result is not None:
                raise ValueError("generate_json result has an invalid output shape")
        elif not isinstance(embedding_result, dict) or output is not None:
            raise ValueError("embed_texts result has an invalid output shape")
        return cls(
            task_id=_required(payload.get("task_id"), "result.task_id"),
            task_kind=task_kind,
            status="completed",
            operation=_required(payload.get("operation"), "result.operation"),
            operation_input=(
                dict(operation_input) if operation_input is not None else None
            ),
            output=dict(output) if output is not None else None,
            embedding_result=(
                dict(embedding_result) if embedding_result is not None else None
            ),
            egress_audit=dict(audit),
            error_code=(
                _required(payload["error_code"], "result.error_code")
                if payload.get("error_code") is not None
                else None
            ),
            raw_model_text=(
                raw_model_text if isinstance(raw_model_text, str) else None
            ),
            structured_output_mode=(
                _required(
                    payload["structured_output_mode"],
                    "result.structured_output_mode",
                )
                if payload.get("structured_output_mode") is not None
                else None
            ),
            contract_digest=(
                _required(payload["contract_digest"], "result.contract_digest")
                if payload.get("contract_digest") is not None
                else None
            ),
            tool_name=(
                _required(payload["tool_name"], "result.tool_name")
                if payload.get("tool_name") is not None
                else None
            ),
            metadata=(dict(metadata) if isinstance(metadata, dict) else None),
        )


@dataclass(frozen=True, slots=True)
class PollExecutionTasksCommand:
    request_id: str
    memory_space_id: str
    worker_id: str
    limit: int = 10
    lease_seconds: int = 300

    def to_payload(self) -> dict[str, object]:
        return {
            "memory_space_id": self.memory_space_id,
            "worker_id": self.worker_id,
            "limit": self.limit,
            "lease_seconds": self.lease_seconds,
        }


@dataclass(frozen=True, slots=True)
class PollExecutionTasksResult:
    tasks: tuple[dict[str, Any], ...]
    has_more: bool = False


@dataclass(frozen=True, slots=True)
class SubmitExecutionResultCommand:
    request_id: str
    task_id: str
    memory_space_id: str
    worker_id: str
    result: dict[str, Any]

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "memory_space_id": self.memory_space_id,
            "worker_id": self.worker_id,
            "result": self.result,
        }


@dataclass(frozen=True, slots=True)
class SubmitExecutionResult:
    accepted: bool
    duplicate: bool = False
    status: str = "accepted"


@dataclass(frozen=True, slots=True)
class FailExecutionTaskCommand:
    request_id: str
    task_id: str
    memory_space_id: str
    worker_id: str
    error_code: str
    retryable: bool
    retry_after_seconds: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "memory_space_id": self.memory_space_id,
            "worker_id": self.worker_id,
            "error_code": self.error_code,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
        }


@dataclass(frozen=True, slots=True)
class FailExecutionTaskResult:
    released: bool
    retry_scheduled: bool = False
    terminal: bool = False
    status: str = "failed"


@dataclass(frozen=True, slots=True)
class RetrieveContextCommand:
    request_id: str
    memory_space_id: str
    query_text: str
    query_embedding: tuple[float, ...]
    object_query_embedding: tuple[float, ...] | None = None
    embedding_model_id: str = "retrieval-embedder"
    embedding_model_version: str = "1"
    limit: int = 5
    project_id: str | None = None
    repository_id: str | None = None
    task_id: str | None = None
    conversation_id: str | None = None
    query_language: str | None = None
    target_id: str | None = None
    target_alias: str | None = None
    related_object_ids: tuple[str, ...] = ()
    requested_facets: tuple[str, ...] = ()
    explanation_level: str = "compact"

    def __post_init__(self) -> None:
        _required(self.request_id, "request_id")
        _required(self.memory_space_id, "memory_space_id")
        _required(self.query_text, "query_text")
        if not self.query_embedding:
            raise ValueError("query_embedding must not be empty")
        if any(
            not isinstance(component, (int, float))
            or isinstance(component, bool)
            or not math.isfinite(float(component))
            for component in self.query_embedding
        ):
            raise ValueError("query_embedding must contain finite values")
        if self.object_query_embedding is not None:
            if len(self.object_query_embedding) != len(self.query_embedding):
                raise ValueError(
                    "object_query_embedding must match query_embedding dimensions"
                )
            if any(
                not isinstance(component, (int, float))
                or isinstance(component, bool)
                or not math.isfinite(float(component))
                for component in self.object_query_embedding
            ):
                raise ValueError("object_query_embedding must contain finite values")
        _required(self.embedding_model_id, "embedding_model_id")
        _required(self.embedding_model_version, "embedding_model_version")
        if self.query_language is not None:
            _required(self.query_language, "query_language")
        if self.target_id is not None:
            _required(self.target_id, "target_id")
        if self.target_alias is not None:
            _required(self.target_alias, "target_alias")
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if self.repository_id is not None and self.project_id is None:
            raise ValueError("repository_id requires project_id")
        if self.explanation_level not in {"compact", "none"}:
            raise ValueError("explanation_level must be compact or none")
        if len(set(self.related_object_ids)) != len(self.related_object_ids):
            raise ValueError("related_object_ids must be unique")
        if len(set(self.requested_facets)) != len(self.requested_facets):
            raise ValueError("requested_facets must be unique")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "memory_space_id": self.memory_space_id,
            "query_text": self.query_text,
            "query_embedding": list(self.query_embedding),
            "object_query_embedding": (
                list(self.object_query_embedding)
                if self.object_query_embedding is not None
                else None
            ),
            "embedding_model_id": self.embedding_model_id,
            "embedding_model_version": self.embedding_model_version,
            "limit": self.limit,
            "project_id": self.project_id,
            "repository_id": self.repository_id,
            "task_id": self.task_id,
            "conversation_id": self.conversation_id,
            "query_language": self.query_language,
            "target_id": self.target_id,
            "target_alias": self.target_alias,
            "related_object_ids": list(self.related_object_ids),
            "requested_facets": list(self.requested_facets),
            "explanation_level": self.explanation_level,
        }


@dataclass(frozen=True, slots=True)
class RetrieveContextResult:
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RecordRetrievalOutcomeCommand:
    request_id: str
    retrieval_request_id: str
    candidate_value_ids: tuple[str, ...]
    delivered_value_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _required(self.request_id, "request_id")
        _required(self.retrieval_request_id, "retrieval_request_id")
        if not self.candidate_value_ids:
            raise ValueError("candidate_value_ids must not be empty")
        if len(self.candidate_value_ids) > 100:
            raise ValueError("candidate_value_ids must not exceed 100 entries")
        if len(self.delivered_value_ids) > 100:
            raise ValueError("delivered_value_ids must not exceed 100 entries")
        if len(set(self.candidate_value_ids)) != len(self.candidate_value_ids):
            raise ValueError("candidate_value_ids must be unique")
        if len(set(self.delivered_value_ids)) != len(self.delivered_value_ids):
            raise ValueError("delivered_value_ids must be unique")
        if not set(self.delivered_value_ids).issubset(set(self.candidate_value_ids)):
            raise ValueError("delivered_value_ids must be a subset of candidates")
        for value_id in (*self.candidate_value_ids, *self.delivered_value_ids):
            _required(value_id, "value_id")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "retrieval_request_id": self.retrieval_request_id,
            "candidate_value_ids": list(self.candidate_value_ids),
            "delivered_value_ids": list(self.delivered_value_ids),
        }


@dataclass(frozen=True, slots=True)
class CoreHealth:
    healthy: bool
    backend: str
    detail: str | None = None
    protocol_version: int | None = None
    schema_version: int | None = None


@dataclass(frozen=True, slots=True)
class RunControlMaintenanceCommand:
    request_id: str
    embedding_profiles: dict[str, dict[str, Any]] | None = None
    retry_failed_round_semantic: bool = False
    retry_limit: int = 100
    retry_error_code: str | None = None
    retry_memory_space_id: str | None = None
    retry_only: bool = False
    automatic_recovery: bool = False

    def __post_init__(self) -> None:
        _required(self.request_id, "request_id")
        if self.embedding_profiles is not None:
            if not isinstance(self.embedding_profiles, dict):
                raise TypeError("embedding_profiles must be an object")
            if any(
                not isinstance(memory_space_id, str)
                or not memory_space_id.strip()
                or not isinstance(profile, dict)
                for memory_space_id, profile in self.embedding_profiles.items()
            ):
                raise TypeError("embedding_profiles must map ids to objects")
        if not isinstance(self.retry_failed_round_semantic, bool):
            raise TypeError("retry_failed_round_semantic must be boolean")
        if not isinstance(self.retry_limit, int) or not 1 <= self.retry_limit <= 1_000:
            raise ValueError("retry_limit must be between 1 and 1000")
        if self.retry_error_code is not None:
            _required(self.retry_error_code, "retry_error_code")
            if len(self.retry_error_code) > 128:
                raise ValueError("retry_error_code must not exceed 128 characters")
        if self.retry_memory_space_id is not None:
            _required(self.retry_memory_space_id, "retry_memory_space_id")
            if len(self.retry_memory_space_id) > 200:
                raise ValueError("retry_memory_space_id must not exceed 200 characters")
        if not isinstance(self.retry_only, bool):
            raise TypeError("retry_only must be boolean")
        if not isinstance(self.automatic_recovery, bool):
            raise TypeError("automatic_recovery must be boolean")
        if self.retry_only and not self.retry_failed_round_semantic:
            raise ValueError("retry_only requires retry_failed_round_semantic")
        if self.automatic_recovery and not self.retry_failed_round_semantic:
            raise ValueError("automatic_recovery requires retry_failed_round_semantic")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.embedding_profiles is not None:
            payload["embedding_profiles"] = self.embedding_profiles
        if self.retry_failed_round_semantic:
            payload["retry_failed_round_semantic"] = True
            payload["retry_limit"] = self.retry_limit
            if self.retry_error_code is not None:
                payload["retry_error_code"] = self.retry_error_code
            if self.retry_memory_space_id is not None:
                payload["retry_memory_space_id"] = self.retry_memory_space_id
            if self.retry_only:
                payload["retry_only"] = True
            if self.automatic_recovery:
                payload["automatic_recovery"] = True
        return payload


@dataclass(frozen=True, slots=True)
class ControlMaintenanceResult:
    status: str
    memory_echoes_reconciled: int
    stats_rebuilt: int
    stale_jobs_recovered: int
    findings_created: int
    duplicate_object_findings: int
    missing_card_embeddings: int
    missing_facet_embeddings: int
    integrity_errors: int
    diagnostic_rows_deleted: int = 0
    terminal_task_rows_deleted: int = 0
    cleanup_candidate_count: int = 0
    objects_consolidated: int = 0
    retried_failed_round_semantic: int = 0

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ControlMaintenanceResult:
        _strict_mapping(
            payload,
            {
                "status",
                "memory_echoes_reconciled",
                "stats_rebuilt",
                "stale_jobs_recovered",
                "findings_created",
                "duplicate_object_findings",
                "objects_consolidated",
                "missing_card_embeddings",
                "missing_facet_embeddings",
                "integrity_errors",
                "diagnostic_rows_deleted",
                "terminal_task_rows_deleted",
                "cleanup_candidate_count",
                "retried_failed_round_semantic",
            },
            "control maintenance result",
        )
        if payload.get("status") != "completed":
            raise ValueError("control maintenance status must be completed")
        return cls(
            status="completed",
            memory_echoes_reconciled=_non_negative_int(
                payload.get("memory_echoes_reconciled"), "memory_echoes_reconciled"
            ),
            stats_rebuilt=_non_negative_int(
                payload.get("stats_rebuilt"), "stats_rebuilt"
            ),
            stale_jobs_recovered=_non_negative_int(
                payload.get("stale_jobs_recovered"), "stale_jobs_recovered"
            ),
            findings_created=_non_negative_int(
                payload.get("findings_created"), "findings_created"
            ),
            duplicate_object_findings=_non_negative_int(
                payload.get("duplicate_object_findings"), "duplicate_object_findings"
            ),
            objects_consolidated=_non_negative_int(
                payload.get("objects_consolidated", 0), "objects_consolidated"
            ),
            retried_failed_round_semantic=_non_negative_int(
                payload.get("retried_failed_round_semantic", 0),
                "retried_failed_round_semantic",
            ),
            missing_card_embeddings=_non_negative_int(
                payload.get("missing_card_embeddings"), "missing_card_embeddings"
            ),
            missing_facet_embeddings=_non_negative_int(
                payload.get("missing_facet_embeddings"), "missing_facet_embeddings"
            ),
            integrity_errors=_non_negative_int(
                payload.get("integrity_errors"), "integrity_errors"
            ),
            diagnostic_rows_deleted=_non_negative_int(
                payload.get("diagnostic_rows_deleted", 0), "diagnostic_rows_deleted"
            ),
            terminal_task_rows_deleted=_non_negative_int(
                payload.get("terminal_task_rows_deleted", 0),
                "terminal_task_rows_deleted",
            ),
            cleanup_candidate_count=_non_negative_int(
                payload.get("cleanup_candidate_count", 0), "cleanup_candidate_count"
            ),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "memory_echoes_reconciled": self.memory_echoes_reconciled,
            "stats_rebuilt": self.stats_rebuilt,
            "stale_jobs_recovered": self.stale_jobs_recovered,
            "findings_created": self.findings_created,
            "duplicate_object_findings": self.duplicate_object_findings,
            "missing_card_embeddings": self.missing_card_embeddings,
            "missing_facet_embeddings": self.missing_facet_embeddings,
            "integrity_errors": self.integrity_errors,
            "diagnostic_rows_deleted": self.diagnostic_rows_deleted,
            "terminal_task_rows_deleted": self.terminal_task_rows_deleted,
            "cleanup_candidate_count": self.cleanup_candidate_count,
        }


@dataclass(frozen=True, slots=True)
class ObjectFacetStatistics:
    object_count: int
    active_value_count: int
    superseded_value_count: int
    operational_backlog: int
    background_backlog: int
    embedding_backlog: int
    integrity_finding_count: int
    blocking_integrity_finding_count: int
    missing_card_embeddings: int | None = None
    missing_facet_embeddings: int | None = None
    legacy_digest_upgrade_required: bool = False
    knowledge_row_count: int = 0
    execution_row_count: int = 0
    diagnostic_row_count: int = 0
    legacy_row_count: int = 0
    database_bytes: int = 0
    oldest_diagnostic: str | None = None
    diagnostic_cleanup_candidate_count: int = 0

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ObjectFacetStatistics:
        _strict_mapping(
            payload,
            {
                "object_count",
                "active_value_count",
                "superseded_value_count",
                "operational_backlog",
                "background_backlog",
                "embedding_backlog",
                "integrity_finding_count",
                "blocking_integrity_finding_count",
                "missing_card_embeddings",
                "missing_facet_embeddings",
                "legacy_digest_upgrade_required",
                "knowledge_row_count",
                "execution_row_count",
                "diagnostic_row_count",
                "legacy_row_count",
                "database_bytes",
                "oldest_diagnostic",
                "diagnostic_cleanup_candidate_count",
            },
            "object-facet statistics",
        )

        def optional_count(name: str) -> int | None:
            value = payload.get(name)
            return None if value is None else _non_negative_int(value, name)

        legacy = payload.get("legacy_digest_upgrade_required", False)
        if not isinstance(legacy, bool):
            raise TypeError("legacy_digest_upgrade_required must be a boolean")
        integrity_finding_count = _non_negative_int(
            payload.get("integrity_finding_count"), "integrity_finding_count"
        )
        blocking_integrity_finding_count = _non_negative_int(
            payload.get(
                "blocking_integrity_finding_count", integrity_finding_count
            ),
            "blocking_integrity_finding_count",
        )
        if blocking_integrity_finding_count > integrity_finding_count:
            raise ValueError(
                "blocking_integrity_finding_count must not exceed "
                "integrity_finding_count"
            )
        return cls(
            object_count=_non_negative_int(payload.get("object_count"), "object_count"),
            active_value_count=_non_negative_int(
                payload.get("active_value_count"), "active_value_count"
            ),
            superseded_value_count=_non_negative_int(
                payload.get("superseded_value_count"), "superseded_value_count"
            ),
            operational_backlog=_non_negative_int(
                payload.get("operational_backlog"), "operational_backlog"
            ),
            background_backlog=_non_negative_int(
                payload.get("background_backlog"), "background_backlog"
            ),
            embedding_backlog=_non_negative_int(
                payload.get("embedding_backlog"), "embedding_backlog"
            ),
            integrity_finding_count=integrity_finding_count,
            blocking_integrity_finding_count=blocking_integrity_finding_count,
            missing_card_embeddings=optional_count("missing_card_embeddings"),
            missing_facet_embeddings=optional_count("missing_facet_embeddings"),
            legacy_digest_upgrade_required=legacy,
            knowledge_row_count=_non_negative_int(
                payload.get("knowledge_row_count", 0), "knowledge_row_count"
            ),
            execution_row_count=_non_negative_int(
                payload.get("execution_row_count", 0), "execution_row_count"
            ),
            diagnostic_row_count=_non_negative_int(
                payload.get("diagnostic_row_count", 0), "diagnostic_row_count"
            ),
            legacy_row_count=_non_negative_int(
                payload.get("legacy_row_count", 0), "legacy_row_count"
            ),
            database_bytes=_non_negative_int(
                payload.get("database_bytes", 0), "database_bytes"
            ),
            oldest_diagnostic=(
                None
                if payload.get("oldest_diagnostic") is None
                else str(payload["oldest_diagnostic"])
            ),
            diagnostic_cleanup_candidate_count=_non_negative_int(
                payload.get("diagnostic_cleanup_candidate_count", 0),
                "diagnostic_cleanup_candidate_count",
            ),
        )


__all__ = [
    "ControlMaintenanceResult",
    "CoreCapabilityError",
    "CoreExecutionResult",
    "CoreExecutionTask",
    "CoreGatewayError",
    "CoreHealth",
    "DomainRejectedError",
    "FailExecutionTaskCommand",
    "FailExecutionTaskResult",
    "IngestRawRoundCommand",
    "IngestRawRoundResult",
    "ObjectFacetStatistics",
    "PollExecutionTasksCommand",
    "PollExecutionTasksResult",
    "RecordRetrievalOutcomeCommand",
    "RetrieveContextCommand",
    "RetrieveContextResult",
    "RunControlMaintenanceCommand",
    "SubmitExecutionResult",
    "SubmitExecutionResultCommand",
    "TransientCoreError",
]
