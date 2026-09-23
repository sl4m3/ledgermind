"""OpenAI-compatible structured completion transport.

The endpoint family shares an HTTP envelope, but does not share support for
structured output modes or request parameter names.  Builders and parsers are
kept separate so capability decisions remain explicit at the Local boundary.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping
from urllib.parse import urlparse

import httpx

from ..cancellation import CancellationToken
from ..profiles import TokenParameter
from ..provider_telemetry import record_http_attempt
from ..strict import STRICT_JSON_SCHEMA_MODE
from .base import (
    InferenceProvider,
    ModelRequest,
    ModelResponse,
    ProviderAuthenticationError,
    ProviderCancelledError,
    ProviderConfigurationError,
    ProviderLengthTruncationError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderTransportError,
    TransientProviderError,
    normalize_error,
    normalize_usage,
)

DEFAULT_TOOL_NAME = "submit_structured_result"
OPENROUTER_SITE_URL = "https://ledgermind.org"
OPENROUTER_APP_TITLE = "LedgerMind"
_PROMPT_ONLY_SUFFIX = (
    "\n\nReturn only one JSON object. Do not use Markdown. Do not add explanations."
)


def provider_request_headers(endpoint: str, api_key: str) -> dict[str, str]:
    """Build provider headers and identify LedgerMind to OpenRouter."""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    host = (urlparse(endpoint).hostname or "").casefold().rstrip(".")
    if host in {"openrouter.ai", "www.openrouter.ai"}:
        headers["HTTP-Referer"] = OPENROUTER_SITE_URL
        headers["X-Title"] = OPENROUTER_APP_TITLE
    return headers


def _contract_schema(request: ModelRequest) -> dict[str, object]:
    contract = request.output_contract
    schema = contract.get("json_schema") if isinstance(contract, dict) else None
    if not isinstance(schema, dict) and isinstance(request.response_format, dict):
        response_schema = request.response_format.get("json_schema")
        if isinstance(response_schema, dict):
            schema = response_schema.get("schema")
    if not isinstance(schema, dict):
        raise ProviderConfigurationError(
            "json_schema mode requires an output contract schema"
        )
    return schema


def _contract_name(request: ModelRequest) -> str:
    contract = request.output_contract
    if isinstance(contract, dict):
        name = contract.get("contract_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    if isinstance(request.response_format, dict):
        response_schema = request.response_format.get("json_schema")
        if isinstance(response_schema, dict):
            name = response_schema.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return "structured_result"


def _token_parameter(request: ModelRequest) -> TokenParameter:
    return request.token_parameter or "max_tokens"


def _messages_payload(
    request: ModelRequest,
    *,
    prompt_only: bool = False,
) -> list[dict[str, str]]:
    supports_system_role = request.supports_system_role is not False
    messages: list[dict[str, str]] = []
    for message in request.messages:
        role = message.role
        if role == "system" and not supports_system_role:
            role = "user"
        messages.append({"role": role, "content": message.content})
    if prompt_only:
        if not messages:
            raise ProviderConfigurationError("prompt_only mode requires messages")
        messages[-1]["content"] += _PROMPT_ONLY_SUFFIX
    return messages


def _base_payload(
    request: ModelRequest, *, prompt_only: bool = False
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": request.model,
        "messages": _messages_payload(request, prompt_only=prompt_only),
    }
    token_parameter = _token_parameter(request)
    payload[token_parameter] = request.max_output_tokens
    if request.supports_seed and request.seed is not None:
        payload["seed"] = request.seed
    return payload


def build_payload_json_schema(request: ModelRequest) -> dict[str, object]:
    """Build the strict JSON Schema request payload."""

    payload = _base_payload(request)
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": _contract_name(request),
            "strict": True,
            "schema": _contract_schema(request),
        },
    }
    return payload


def build_payload_tool_call(request: ModelRequest) -> dict[str, object]:
    """Build a forced single-function tool-call payload."""

    payload = _base_payload(request)
    tool_name = request.tool_name or DEFAULT_TOOL_NAME
    parameters: dict[str, object] = {}
    if isinstance(request.output_contract, dict):
        schema = request.output_contract.get("json_schema")
        if isinstance(schema, dict):
            parameters = schema
    payload["tools"] = [
        {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": "Return the requested structured result",
                "parameters": parameters,
            },
        }
    ]
    payload["tool_choice"] = {
        "type": "function",
        "function": {"name": tool_name},
    }
    return payload


def build_payload_json_object(request: ModelRequest) -> dict[str, object]:
    """Build the legacy JSON-object payload."""

    payload = _base_payload(request)
    payload["response_format"] = {"type": "json_object"}
    return payload


def build_payload_prompt_only(request: ModelRequest) -> dict[str, object]:
    """Build a payload relying only on the prompt's JSON instructions."""

    return _base_payload(request, prompt_only=True)


def build_payload(request: ModelRequest) -> dict[str, object]:
    """Dispatch to the explicit payload builder for ``request.mode``."""

    if request.response_format is not None:
        format_type = request.response_format.get("type")
        if format_type == "json_object":
            return build_payload_json_object(request)
        if format_type == "json_schema":
            return build_payload_json_schema(request)
        raise ProviderConfigurationError("unsupported response format")
    mode = request.mode
    if mode in {STRICT_JSON_SCHEMA_MODE, "json_schema"}:
        return build_payload_json_schema(request)
    if mode == "tool_call":
        return build_payload_tool_call(request)
    if mode == "prompt_only":
        return build_payload_prompt_only(request)
    # ``auto`` is useful when a request is constructed directly.  Runtime
    # selection normally resolves it before a provider is called.
    return build_payload_json_object(request)


def _choice_finish_reason(response: Mapping[str, object]) -> str | None:
    """Read the first choice's finish reason without touching payload data."""
    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        reason = choices[0].get("finish_reason")
        return reason if isinstance(reason, str) else None
    return None


def _message_from_response(response: Mapping[str, object]) -> Mapping[str, object]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderResponseError("provider response has no choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ProviderResponseError("provider response choice is invalid")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ProviderResponseError("provider response message is invalid")
    return message


def parse_content_response(response: Mapping[str, object]) -> str:
    """Extract content from an OpenAI-compatible response envelope."""

    message = _message_from_response(response)
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderResponseError("provider response content is missing")
    return content


def parse_tool_call_response(
    response: Mapping[str, object],
    *,
    expected_tool_name: str | None = None,
) -> str:
    """Extract the first function's JSON arguments from ``tool_calls``."""

    message = _message_from_response(response)
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        raise ProviderResponseError("provider response has no tool calls")
    first_call = tool_calls[0]
    if not isinstance(first_call, dict):
        raise ProviderResponseError("provider tool call is invalid")
    function = first_call.get("function")
    if not isinstance(function, dict):
        raise ProviderResponseError("provider tool call function is invalid")
    name = function.get("name")
    if expected_tool_name is not None and name != expected_tool_name:
        raise ProviderResponseError("provider returned an unexpected tool name")
    arguments = function.get("arguments")
    if isinstance(arguments, dict):
        arguments = json.dumps(
            arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    if not isinstance(arguments, str) or not arguments.strip():
        raise ProviderResponseError("provider tool arguments are missing")
    return arguments


def strip_json_fence(content: str) -> str:
    """Remove one complete Markdown JSON fence without repairing its shape."""

    normalized = content.strip()
    if not normalized.startswith("```"):
        return normalized
    lines = normalized.splitlines()
    if len(lines) < 3 or not lines[-1].strip() == "```":
        raise ProviderResponseError("provider JSON fence is incomplete")
    language = lines[0].strip()[3:].strip().lower()
    if language not in {"", "json"}:
        raise ProviderResponseError("provider returned an unsupported code fence")
    inner = "\n".join(lines[1:-1]).strip()
    if not inner:
        raise ProviderResponseError("provider JSON content is empty")
    return inner


def decode_json_content(content: str) -> object:
    """Decode JSON after the one permitted code-fence normalization."""

    normalized = strip_json_fence(content)
    try:
        return json.loads(normalized)
    except ValueError as exc:
        raise ProviderResponseError("provider returned invalid JSON content") from exc


def _safe_metadata(
    envelope: Mapping[str, object],
    response: httpx.Response,
) -> dict[str, object]:
    """Keep only known response metadata; never copy arbitrary provider data."""

    metadata: dict[str, object] = {}
    request_id = response.headers.get("x-request-id") or response.headers.get(
        "request-id"
    )
    if request_id:
        metadata["request_id"] = request_id
    for key in ("id", "created", "system_fingerprint", "provider"):
        value = envelope.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            metadata[key] = value
    usage = envelope.get("usage")
    if isinstance(usage, dict):
        safe_usage: dict[str, object] = {}
        for key, value in usage.items():
            if (
                isinstance(key, str)
                and isinstance(value, int)
                and not isinstance(value, bool)
            ):
                safe_usage[key] = value
            elif (
                key in {"reported_cost", "cost", "cost_usd"}
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value >= 0
            ):
                safe_usage[key] = float(value)
        if safe_usage:
            metadata["usage"] = safe_usage
    choices = envelope.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        finish_reason = choices[0].get("finish_reason")
        if isinstance(finish_reason, str):
            metadata["finish_reason"] = finish_reason
    return metadata


def _safe_response_provider(response: httpx.Response) -> str | None:
    """Read only OpenRouter's non-secret provider label for diagnostics."""

    try:
        envelope = response.json()
    except ValueError:
        return None
    if not isinstance(envelope, Mapping):
        return None
    value = envelope.get("provider")
    return value.strip() if isinstance(value, str) and value.strip() else None


class OpenAICompatibleProvider(InferenceProvider):
    """Synchronous provider for OpenAI-compatible ``/chat/completions`` APIs."""

    provider_kind = "openai_compatible"

    # Keep builders/parsers discoverable on the concrete provider for callers
    # that do not need to instantiate an HTTP client.
    build_payload_json_schema = staticmethod(build_payload_json_schema)
    build_payload_tool_call = staticmethod(build_payload_tool_call)
    build_payload_json_object = staticmethod(build_payload_json_object)
    build_payload_prompt_only = staticmethod(build_payload_prompt_only)
    parse_content_response = staticmethod(parse_content_response)
    parse_tool_call_response = staticmethod(parse_tool_call_response)
    normalize_usage = staticmethod(normalize_usage)
    normalize_error = staticmethod(normalize_error)

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        max_response_bytes: int = 2_000_000,
        retry_delay_seconds: float = 0.25,
        connect_timeout_seconds: float | None = None,
        read_timeout_seconds: float | None = None,
        write_timeout_seconds: float | None = None,
        pool_timeout_seconds: float | None = None,
        token_parameter: TokenParameter = "max_tokens",
        supports_system_role: bool = True,
        supports_seed: bool = False,
        extra_body: Mapping[str, object] | None = None,
        strict_transport: str | None = None,
        profile_fingerprint: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        normalized_url = base_url.strip().rstrip("/")
        parsed = urlparse(normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ProviderConfigurationError("base_url must be an absolute http(s) URL")
        if not api_key:
            raise ProviderConfigurationError("provider secret is not configured")
        if timeout_seconds <= 0 or timeout_seconds > 600:
            raise ProviderConfigurationError(
                "timeout_seconds is outside the supported range"
            )
        if max_retries < 0 or max_retries > 5:
            raise ProviderConfigurationError(
                "max_retries is outside the supported range"
            )
        if max_response_bytes <= 0:
            raise ProviderConfigurationError("max_response_bytes must be positive")
        if retry_delay_seconds < 0 or retry_delay_seconds > 30:
            raise ProviderConfigurationError(
                "retry_delay_seconds is outside the supported range"
            )
        if token_parameter not in {"max_tokens", "max_completion_tokens"}:
            raise ProviderConfigurationError("unsupported token parameter")
        timeout_values = {
            "connect_timeout_seconds": (
                timeout_seconds
                if connect_timeout_seconds is None
                else float(connect_timeout_seconds)
            ),
            "read_timeout_seconds": (
                timeout_seconds
                if read_timeout_seconds is None
                else float(read_timeout_seconds)
            ),
            "write_timeout_seconds": (
                timeout_seconds
                if write_timeout_seconds is None
                else float(write_timeout_seconds)
            ),
            "pool_timeout_seconds": (
                timeout_seconds
                if pool_timeout_seconds is None
                else float(pool_timeout_seconds)
            ),
        }
        for timeout_name, timeout_value in timeout_values.items():
            if timeout_value <= 0 or timeout_value > 600:
                raise ProviderConfigurationError(
                    f"{timeout_name} is outside the supported range"
                )

        self.base_url = normalized_url
        self._api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.max_response_bytes = int(max_response_bytes)
        self.retry_delay_seconds = float(retry_delay_seconds)
        self.token_parameter = token_parameter
        self.supports_system_role = bool(supports_system_role)
        self.supports_seed = bool(supports_seed)
        self.extra_body = dict(extra_body or {})
        self.strict_transport = strict_transport
        if strict_transport is not None and strict_transport != "nvidia_guided_json":
            raise ProviderConfigurationError("unsupported strict provider adapter")
        if strict_transport == "nvidia_guided_json":
            self.provider_kind = "nvidia_nim"
        self.profile_fingerprint = profile_fingerprint
        self.timeout = httpx.Timeout(
            self.timeout_seconds,
            connect=timeout_values["connect_timeout_seconds"],
            read=timeout_values["read_timeout_seconds"],
            write=timeout_values["write_timeout_seconds"],
            pool=timeout_values["pool_timeout_seconds"],
        )
        self._client = client or httpx.Client(timeout=self.timeout)
        self._owns_client = client is None

    def __repr__(self) -> str:
        return (
            "OpenAICompatibleProvider("
            f"base_url={self.base_url!r}, max_retries={self.max_retries}, "
            f"max_response_bytes={self.max_response_bytes})"
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _prepare_request(self, request: ModelRequest) -> ModelRequest:
        updates: dict[str, object] = {}
        if request.token_parameter is None:
            updates["token_parameter"] = self.token_parameter
        if request.supports_system_role is None:
            updates["supports_system_role"] = self.supports_system_role
        if request.supports_seed is None:
            updates["supports_seed"] = self.supports_seed
        if request.response_format is not None:
            format_type = request.response_format.get("type")
            if format_type == "json_object":
                updates["mode"] = "json_object"
            elif (
                format_type == "json_schema" and request.mode != STRICT_JSON_SCHEMA_MODE
            ):
                updates["mode"] = "json_schema"
        if request.mode == "auto" and request.response_format is None:
            updates["mode"] = "json_object"
        return request.model_copy(update=updates) if updates else request

    def _request(
        self,
        request: ModelRequest,
        *,
        token: CancellationToken | None = None,
    ) -> ModelResponse:
        _raise_if_cancelled(token)
        prepared = self._prepare_request(request)
        if (
            prepared.mode == STRICT_JSON_SCHEMA_MODE
            and self.strict_transport == "nvidia_guided_json"
        ):
            payload = build_payload_json_schema(prepared)
            payload.pop("response_format", None)
            payload["guided_json"] = _contract_schema(prepared)
        else:
            payload = prepared.to_openai_payload()
        # Provider-specific controls are kept outside the Core request
        # contract.  Core-generated transport fields remain authoritative so
        # an option blob cannot weaken the JSON contract or redirect a task.
        for key, value in self.extra_body.items():
            if key not in payload:
                payload[key] = value
        request_bytes = len(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        from ..provider_telemetry import current_operation

        operation = current_operation() or prepared.metadata.get(
            "_ledgermind_operation", "capability_probe"
        )
        profile_fingerprint = prepared.metadata.get(
            "_ledgermind_profile_fingerprint", self.profile_fingerprint
        )
        provider_options = self.extra_body.get("provider")
        configured_routes: tuple[str, ...] = ()
        if isinstance(provider_options, Mapping):
            route_order = provider_options.get("order")
            if isinstance(route_order, (list, tuple)):
                configured_routes = tuple(
                    route.strip()
                    for route in route_order
                    if isinstance(route, str) and route.strip()
                )
        attempts = 0
        for attempt in range(1, self.max_retries + 2):
            _raise_if_cancelled(token)
            attempts = attempt
            started = time.perf_counter()
            try:
                response = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers=provider_request_headers(self.base_url, self._api_key),
                    json=payload,
                    timeout=self.timeout,
                )
            except httpx.TimeoutException as exc:
                record_http_attempt(
                    kind="generation",
                    operation=operation,
                    provider_profile_fingerprint=profile_fingerprint,
                    transport=self.provider_kind,
                    model=prepared.model,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    status="timeout",
                    retry_index=attempt - 1,
                    metadata=prepared.metadata,
                    configured_routes=configured_routes,
                )
                if attempt <= self.max_retries:
                    self._sleep_before_retry(attempt, token=token)
                    continue
                raise ProviderTimeoutError("provider request timed out") from exc
            except httpx.RequestError as exc:
                record_http_attempt(
                    kind="generation",
                    operation=operation,
                    provider_profile_fingerprint=profile_fingerprint,
                    transport=self.provider_kind,
                    model=prepared.model,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    status="transport_error",
                    retry_index=attempt - 1,
                    metadata=prepared.metadata,
                    configured_routes=configured_routes,
                )
                if attempt <= self.max_retries:
                    self._sleep_before_retry(attempt, token=token)
                    continue
                raise ProviderTransportError("provider transport failed") from exc

            request_id = (
                response.headers.get("x-request-id")
                or response.headers.get("request-id")
                or f"local-{uuid.uuid4().hex}"
            )
            if response.status_code >= 400:
                record_http_attempt(
                    kind="generation",
                    operation=operation,
                    provider_profile_fingerprint=profile_fingerprint,
                    transport=self.provider_kind,
                    model=prepared.model,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    status="failed",
                    request_id=request_id,
                    http_status=response.status_code,
                    retry_index=attempt - 1,
                    metadata=prepared.metadata,
                    configured_routes=configured_routes,
                )
            if response.status_code in {401, 403}:
                raise ProviderAuthenticationError("provider authentication failed")
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt <= self.max_retries:
                    self._sleep_before_retry(attempt, token=token)
                    continue
                raise TransientProviderError(
                    f"provider returned temporary HTTP status {response.status_code}"
                )
            if response.status_code >= 400:
                raise ProviderResponseError(
                    f"provider returned HTTP status {response.status_code}"
                )

            response_bytes = len(response.content)
            if response_bytes > self.max_response_bytes:
                record_http_attempt(
                    kind="generation",
                    operation=operation,
                    provider_profile_fingerprint=profile_fingerprint,
                    transport=self.provider_kind,
                    model=prepared.model,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    status="failed",
                    request_id=request_id,
                    http_status=response.status_code,
                    retry_index=attempt - 1,
                    metadata=prepared.metadata,
                    configured_routes=configured_routes,
                )
                raise ProviderResponseError("provider response exceeds size limit")
            try:
                result = self._parse_response(
                    response,
                    request=prepared,
                    attempts=attempts,
                    request_bytes=request_bytes,
                    response_bytes=response_bytes,
                )
            except Exception:
                record_http_attempt(
                    kind="generation",
                    operation=operation,
                    provider_profile_fingerprint=profile_fingerprint,
                    transport=self.provider_kind,
                    model=prepared.model,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    status="invalid_response",
                    request_id=request_id,
                    http_status=response.status_code,
                    retry_index=attempt - 1,
                    metadata=prepared.metadata,
                    configured_routes=configured_routes,
                    served_by=_safe_response_provider(response),
                )
                raise
            normalized_usage = normalize_usage(result)
            record_http_attempt(
                kind="generation",
                operation=operation,
                provider_profile_fingerprint=profile_fingerprint,
                transport=self.provider_kind,
                model=result.model,
                duration_ms=(time.perf_counter() - started) * 1000,
                status="completed",
                request_id=request_id,
                http_status=response.status_code,
                input_tokens=(
                    normalized_usage.get("input_tokens")
                    if isinstance(normalized_usage.get("input_tokens"), int)
                    else None
                ),
                output_tokens=(
                    normalized_usage.get("output_tokens")
                    if isinstance(normalized_usage.get("output_tokens"), int)
                    else None
                ),
                total_tokens=(
                    normalized_usage.get("total_tokens")
                    if isinstance(normalized_usage.get("total_tokens"), int)
                    else None
                ),
                cached_input_tokens=(
                    normalized_usage.get("cached_input_tokens")
                    if isinstance(normalized_usage.get("cached_input_tokens"), int)
                    else None
                ),
                reported_cost=(
                    normalized_usage.get("reported_cost")
                    if isinstance(normalized_usage.get("reported_cost"), (int, float))
                    else None
                ),
                usage_unknown=bool(normalized_usage.get("usage_unknown", True)),
                retry_index=attempt - 1,
                metadata=prepared.metadata,
                configured_routes=configured_routes,
                served_by=result.metadata.get("provider"),
                wire_reasoning_effort=payload.get("reasoning_effort"),
                wire_thinking=(
                    payload["thinking"].get("type")
                    if isinstance(payload.get("thinking"), Mapping)
                    else None
                ),
            )
            return result

        raise ProviderTransportError("provider request did not complete")

    def _sleep_before_retry(
        self,
        attempt: int,
        *,
        token: CancellationToken | None = None,
    ) -> None:
        delay = min(self.retry_delay_seconds * attempt, 30.0)
        if token is not None:
            _raise_if_cancelled(token)
            if token.wait(delay):
                raise ProviderCancelledError()
        elif delay:
            time.sleep(delay)

    @staticmethod
    def _parse_response(
        response: httpx.Response,
        *,
        request: ModelRequest,
        attempts: int,
        request_bytes: int,
        response_bytes: int,
    ) -> ModelResponse:
        try:
            envelope = response.json()
        except ValueError as exc:
            raise ProviderResponseError(
                "provider returned invalid response JSON"
            ) from exc
        if not isinstance(envelope, dict):
            raise ProviderResponseError("provider response envelope is invalid")

        if request.mode == "tool_call":
            content = parse_tool_call_response(
                envelope, expected_tool_name=request.tool_name or DEFAULT_TOOL_NAME
            )
        else:
            content = parse_content_response(envelope)
        try:
            decoded = decode_json_content(content)
        except ProviderResponseError as exc:
            if _choice_finish_reason(envelope) == "length":
                raise ProviderLengthTruncationError(
                    "provider output truncated at token limit"
                ) from exc
            raise
        if not isinstance(decoded, (dict, list)):
            raise ProviderResponseError(
                "provider JSON content must be an object or array"
            )
        response_model = envelope.get("model", request.model)
        if not isinstance(response_model, str) or not response_model:
            response_model = request.model
        return ModelResponse(
            content=content,
            raw_text=content,
            model=response_model,
            attempts=attempts,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            status_code=response.status_code,
            output_contract=request.output_contract,
            mode=request.mode,
            tool_name=(
                request.tool_name
                or (DEFAULT_TOOL_NAME if request.mode == "tool_call" else None)
            ),
            metadata=_safe_metadata(envelope, response),
        )

    def complete_json(
        self,
        request: ModelRequest,
        token: CancellationToken | None = None,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelResponse:
        if (
            token is not None
            and cancellation_token is not None
            and token is not cancellation_token
        ):
            raise ValueError("conflicting cancellation tokens")
        active_token = cancellation_token or token
        return self._request(request, token=active_token)

    def execute_structured(
        self,
        task: ModelRequest,
        profile: object,
        capabilities: object | None = None,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> ModelResponse:
        """Implement the provider-neutral GenerationTransport boundary."""

        del profile, capabilities
        return self.complete_json(task, cancellation_token=cancellation_token)

    def probe_capabilities(self, profile: object) -> dict[str, object]:
        """Return transport facts without claiming endpoint feature support.

        Feature support is established by the explicit Local probe. This
        method exists so provider adapters share a stable boundary; it does
        not introduce an implicit network probe into ordinary execution.
        """

        model = getattr(profile, "model", None)
        return {
            "transport": self.provider_kind,
            "model": model if isinstance(model, str) else "",
            "structured_json_schema": False,
            "structured_json_object": False,
            "tool_calling": False,
            "plain_json_prompt": True,
            "native_schema_strictness": False,
            "probe_required": True,
        }


def _raise_if_cancelled(token: CancellationToken | None) -> None:
    if token is not None:
        token.raise_if_cancelled()


__all__ = [
    "DEFAULT_TOOL_NAME",
    "OpenAICompatibleProvider",
    "build_payload",
    "build_payload_json_object",
    "build_payload_json_schema",
    "build_payload_prompt_only",
    "build_payload_tool_call",
    "decode_json_content",
    "parse_content_response",
    "parse_tool_call_response",
    "strip_json_fence",
]
