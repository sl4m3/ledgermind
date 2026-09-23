"""Typed provider boundary for Local inference calls."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Literal, Protocol

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from ..cancellation import CancellationToken
from ..profiles import StructuredOutputMode, TokenParameter


class ChatMessage(BaseModel):
    """One bounded chat message sent to a provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ModelRequest(BaseModel):
    """Strict structured-completion request; never an arbitrary mapping."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True
    )

    model: str = Field(min_length=1, max_length=500)
    messages: tuple[ChatMessage, ...] = Field(min_length=1, max_length=32)
    max_output_tokens: int = Field(gt=0, le=50_000)
    response_format: dict[str, object] | None = None
    output_contract: dict[str, object] | None = None
    structured_output_requirement: dict[str, object] | None = None
    mode: StructuredOutputMode = Field(
        default="json_object",
        validation_alias=AliasChoices("mode", "structured_output_mode"),
    )
    tool_name: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict[str, object] = Field(default_factory=dict)
    token_parameter: TokenParameter | None = None
    supports_system_role: bool | None = None
    supports_seed: bool | None = None
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)

    @field_validator("model")
    @classmethod
    def _normalize_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("model must not be empty")
        return normalized

    @classmethod
    def from_messages(
        cls,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        response_format: dict[str, object] | None = None,
        output_contract: dict[str, object] | None = None,
        structured_output_requirement: dict[str, object] | None = None,
        mode: StructuredOutputMode = "json_object",
        tool_name: str | None = None,
        metadata: dict[str, object] | None = None,
        token_parameter: TokenParameter | None = None,
        supports_system_role: bool | None = None,
        supports_seed: bool | None = None,
        seed: int | None = None,
    ) -> ModelRequest:
        return cls(
            model=model,
            messages=(
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ),
            max_output_tokens=max_output_tokens,
            response_format=response_format,
            output_contract=output_contract,
            structured_output_requirement=structured_output_requirement,
            mode=mode,
            tool_name=tool_name,
            metadata=metadata or {},
            token_parameter=token_parameter,
            supports_system_role=supports_system_role,
            supports_seed=supports_seed,
            seed=seed,
        )

    @property
    def structured_output_mode(self) -> StructuredOutputMode:
        """Compatibility name used by the Core-facing task contract."""

        return self.mode

    def to_openai_payload(self) -> dict[str, object]:
        from .openai_compatible import build_payload

        return build_payload(self)

    def encoded_payload(self) -> bytes:
        return json.dumps(
            self.to_openai_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class ModelResponse(BaseModel):
    """Provider response content and secret-free transport metadata."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True
    )

    content: str = Field(min_length=2)
    model: str = Field(min_length=1)
    attempts: int = Field(ge=1)
    request_bytes: int = Field(ge=0)
    response_bytes: int = Field(ge=0)
    status_code: int = Field(ge=100, le=599)
    output_contract: dict[str, object] | None = None
    mode: StructuredOutputMode = Field(
        default="json_object",
        validation_alias=AliasChoices("mode", "structured_output_mode"),
    )
    tool_name: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict[str, object] = Field(default_factory=dict)
    raw_text: str | None = None

    @property
    def structured_output_mode(self) -> StructuredOutputMode:
        return self.mode

    @property
    def selected_mode(self) -> StructuredOutputMode:
        return self.mode

    @property
    def provider_metadata(self) -> dict[str, object]:
        return self.metadata

    @property
    def raw_model_text(self) -> str:
        return self.raw_text or self.content


def normalize_usage(response: ModelResponse | Mapping[str, object]) -> dict[str, object]:
    """Normalize provider usage without assigning provider-specific costs.

    Providers may call the same counters ``prompt_tokens``/``completion_tokens``
    or ``input_tokens``/``output_tokens``.  Local exposes only token counts and
    marks absent counters explicitly so accounting never turns an unknown value
    into zero.
    """

    if isinstance(response, ModelResponse):
        metadata: Mapping[str, object] = response.metadata
    else:
        metadata = response
    raw = metadata.get("usage")
    usage = raw if isinstance(raw, Mapping) else metadata
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens", "input_token_count"),
        "output_tokens": (
            "output_tokens",
            "completion_tokens",
            "output_token_count",
        ),
        "total_tokens": ("total_tokens", "total_token_count"),
        "cached_input_tokens": ("cached_input_tokens", "cache_read_input_tokens"),
    }
    normalized: dict[str, object] = {}
    for target, names in aliases.items():
        for name in names:
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                normalized[target] = value
                break
    if "cached_input_tokens" not in normalized and isinstance(usage, Mapping):
        for container, field in (
            ("prompt_tokens_details", "cached_tokens"),
            ("input_tokens_details", "cached_tokens"),
            ("runinfra", "cached_input_tokens"),
        ):
            details = usage.get(container)
            value = details.get(field) if isinstance(details, Mapping) else None
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                normalized["cached_input_tokens"] = value
                break
    if isinstance(usage, Mapping):
        for name in ("reported_cost", "cost", "cost_usd"):
            value = usage.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                normalized["reported_cost"] = float(value)
                break
    if "input_tokens" in normalized and "output_tokens" in normalized and "total_tokens" not in normalized:
        normalized["total_tokens"] = int(normalized["input_tokens"]) + int(normalized["output_tokens"])
    normalized["usage_unknown"] = not any(
        key in normalized for key in ("input_tokens", "output_tokens", "total_tokens")
    )
    return normalized


def normalize_error(error: BaseException) -> dict[str, object]:
    """Return content-free, transport-neutral error metadata."""

    code = getattr(error, "code", None)
    if not isinstance(code, str) or not code.strip():
        code = "provider_error"
    status_code = getattr(error, "status_code", None)
    return {
        "code": code,
        "retryable": bool(
            isinstance(error, (ProviderTimeoutError, ProviderTransportError, TransientProviderError))
            or status_code == 429
            or isinstance(status_code, int) and 500 <= status_code <= 599
        ),
        "status_code": status_code if isinstance(status_code, int) else None,
    }


class ProviderError(RuntimeError):
    """Base error with safe, non-payload diagnostics."""

    code = "provider_error"


class ProviderConfigurationError(ProviderError):
    code = "configuration_error"


class ProviderAuthenticationError(ProviderError):
    code = "authentication_error"


class ProviderTimeoutError(ProviderError):
    code = "timeout"


class ProviderCancelledError(ProviderError):
    """Safe provider cancellation signal without request or payload details."""

    code = "cancelled"

    def __init__(self, *args: object) -> None:
        del args
        super().__init__("provider request cancelled")


class ProviderTransportError(ProviderError):
    code = "transport_error"


class TransientProviderError(ProviderError):
    code = "transient_provider_error"


class ProviderResponseError(ProviderError):
    code = "invalid_provider_response"


class ProviderLengthTruncationError(ProviderResponseError):
    code = "length_truncation"


class InferenceProvider(Protocol):
    """Structural interface implemented by concrete model providers."""

    provider_kind: str = "unknown"

    def complete_json(
        self,
        request: ModelRequest,
        token: CancellationToken | None = None,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelResponse: ...


class GenerationTransport(Protocol):
    """Provider-neutral Local transport contract.

    Core-facing code can depend on this interface without knowing endpoint,
    vendor, model, or response-format details. Concrete transports may still
    expose ``complete_json`` for the legacy Local executor adapter.
    """

    provider_kind: str

    def execute_structured(
        self,
        task: ModelRequest,
        profile: object,
        capabilities: object | None = None,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelResponse: ...

    def probe_capabilities(self, profile: object) -> object: ...

    def normalize_usage(self, response: ModelResponse | Mapping[str, object]) -> dict[str, object]: ...

    def normalize_error(self, error: BaseException) -> dict[str, object]: ...


def messages_as_dicts(messages: Iterable[ChatMessage]) -> list[dict[str, str]]:
    """Return a serialization helper without exposing Pydantic internals."""

    return [{"role": message.role, "content": message.content} for message in messages]


__all__ = [
    "ChatMessage",
    "GenerationTransport",
    "InferenceProvider",
    "ModelRequest",
    "ModelResponse",
    "ProviderAuthenticationError",
    "ProviderCancelledError",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderLengthTruncationError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderTransportError",
    "StructuredOutputMode",
    "TokenParameter",
    "TransientProviderError",
    "normalize_error",
    "normalize_usage",
]
