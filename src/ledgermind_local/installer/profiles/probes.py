"""Real provider probes performed by install, configure, and doctor."""

from __future__ import annotations

import json
import math
from typing import Any

import httpx

from ...inference.providers.openai_compatible import provider_request_headers
from ...inference.strict import (
    STRICT_SCHEMA_PROFILE_VERSION,
    canonical_digest,
    validate_strict_schema_profile,
)
from ..errors import ProviderProbeError
from ..models import EmbeddingApiConfig, GenerationConfig
from ..provider_profiles import generation_provider_profile
from .embedding_api import EmbeddingProviderError, OpenAICompatibleEmbeddingProvider


def _response_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
    elif isinstance(error, str):
        message = error
    else:
        message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    return " ".join(message.split())[:300]


def _safe_status(response: httpx.Response) -> None:
    detail = _response_error_detail(response)
    suffix = f": {detail}" if detail else ""
    if response.status_code in {401, 403}:
        raise ProviderProbeError(f"provider authentication failed{suffix}")
    if response.status_code == 404:
        raise ProviderProbeError(f"provider endpoint or model was not found{suffix}")
    if response.status_code == 429:
        raise ProviderProbeError(f"provider rate limit was reached{suffix}")
    if response.status_code >= 400:
        raise ProviderProbeError(
            f"provider returned HTTP {response.status_code}{suffix}"
        )


_STRICT_PROBE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "state": {"type": "string", "enum": ["ok"]},
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {"type": "integer"},
        },
    },
    "required": ["schema_version", "state", "items"],
}

_GENERATION_PROBE_MAX_TOKENS = 256


def _strict_probe_output(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    return (
        set(payload) == {"schema_version", "state", "items"}
        and payload.get("schema_version") == 1
        and payload.get("state") == "ok"
        and isinstance(payload.get("items"), list)
        and 1 <= len(payload["items"]) <= 2
        and all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in payload["items"]
        )
    )


def _empty_generation_detail(payload: object) -> str:
    """Describe an empty successful response without echoing model output."""

    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else {}
    if not isinstance(choice, dict):
        choice = {}
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    completion_details = usage.get("completion_tokens_details")
    if not isinstance(completion_details, dict):
        completion_details = {}
    values = {
        "finish_reason": choice.get("finish_reason"),
        "native_finish_reason": choice.get("native_finish_reason"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": completion_details.get("reasoning_tokens"),
    }
    rendered = ", ".join(
        f"{name}={value!r}" for name, value in values.items() if value is not None
    )
    return f" ({rendered})" if rendered else ""


def _probe_generation_single(
    config: GenerationConfig, *, token: str, client: httpx.Client | None = None
) -> dict[str, Any]:
    if not token:
        raise ProviderProbeError("generation token is empty")
    owns_client = client is None
    active = client or httpx.Client(timeout=config.timeout_seconds)
    try:
        endpoint = config.endpoint.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        request_payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return exactly one JSON object matching the strict capability probe schema.",
                },
                {
                    "role": "user",
                    "content": 'Return {"schema_version":1,"state":"ok","items":[1]}.',
                },
            ],
            # A tiny budget can be consumed entirely by hidden reasoning before
            # the model emits JSON. This probe tests schema transport, not IQ.
            "max_tokens": _GENERATION_PROBE_MAX_TOKENS,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "ledgermind_strict_probe",
                    "strict": True,
                    "schema": _STRICT_PROBE_SCHEMA,
                },
            },
        }
        provider = generation_provider_profile(config.provider_profile)
        request_payload.update(provider.reasoning_extra_body)
        if provider.profile_id == "openrouter":
            if config.route:
                routes = [config.route, *config.fallback_routes]
                request_payload["provider"] = {
                    "order": routes,
                    "only": routes,
                    "allow_fallbacks": bool(config.fallback_routes),
                    "require_parameters": True,
                }
        elif provider.profile_id == "nvidia_nim":
            request_payload.pop("response_format")
            request_payload["guided_json"] = _STRICT_PROBE_SCHEMA
        response = active.post(
            endpoint,
            headers=provider_request_headers(endpoint, token),
            json=request_payload,
            timeout=config.timeout_seconds,
        )
        _safe_status(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderProbeError("generation response is not JSON") from exc
        content = (
            payload.get("choices", [{}])[0].get("message", {}).get("content")
            if isinstance(payload, dict)
            and isinstance(payload.get("choices"), list)
            and payload["choices"]
            else None
        )
        if not isinstance(content, str) or not content.strip():
            raise ProviderProbeError(
                "generation response has no message content"
                + _empty_generation_detail(payload)
            )
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderProbeError(
                "generation provider did not return structured JSON"
            ) from exc
        if not _strict_probe_output(decoded):
            raise ProviderProbeError(
                "generation provider did not satisfy the strict probe schema"
            )
        return {
            "endpoint": config.endpoint,
            "model": payload.get("model", config.model)
            if isinstance(payload, dict)
            else config.model,
            "request_id": response.headers.get("x-request-id")
            or response.headers.get("request-id"),
            "status_code": response.status_code,
            "structured_json": True,
            "strict_structured_outputs": True,
            "route": config.route,
            "schema_profile_version": STRICT_SCHEMA_PROFILE_VERSION,
            "probe_contract_digest": canonical_digest(
                validate_strict_schema_profile(_STRICT_PROBE_SCHEMA)
            ),
        }
    except ProviderProbeError as exc:
        raise ProviderProbeError(
            f"generation probe failed for model {config.model!r} at "
            f"{config.endpoint!r}: {exc}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise ProviderProbeError(
            f"generation probe timed out for model {config.model!r} at "
            f"{config.endpoint!r}"
        ) from exc
    except httpx.RequestError as exc:
        raise ProviderProbeError(
            f"generation probe request failed for model {config.model!r} at "
            f"{config.endpoint!r}: {type(exc).__name__}"
        ) from exc
    finally:
        if owns_client:
            active.close()


def probe_generation(
    config: GenerationConfig, *, token: str, client: httpx.Client | None = None
) -> dict[str, Any]:
    """Verify the one model used by the complete semantic pipeline."""

    result = _probe_generation_single(config, token=token, client=client)
    primary = dict(result)
    primary["probed_models"] = [config.model]
    primary["model_probes"] = [result]
    return primary


def probe_embedding_api(
    config: EmbeddingApiConfig,
    *,
    token: str,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    provider = OpenAICompatibleEmbeddingProvider(
        endpoint=config.endpoint,
        token=token,
        model=config.model,
        dimensions=config.dimensions,
        batch_size=config.batch_size,
        timeout_seconds=config.timeout_seconds,
        client=client,
    )
    try:
        one = provider.embed(("LedgerMind embedding probe",))
        batch = provider.embed(("LedgerMind embedding probe", "LedgerMind batch probe"))
        if len(one) != 1 or len(batch) != 2:
            raise ProviderProbeError("embedding provider returned an invalid batch")
        for vector in (*one, *batch):
            if len(vector) != config.dimensions or not all(
                math.isfinite(value) for value in vector
            ):
                raise ProviderProbeError(
                    "embedding provider returned invalid dimensions or floats"
                )
        return {
            "endpoint": config.endpoint,
            "model": config.model,
            "dimensions": config.dimensions,
            "batch_size": config.batch_size,
            "request_count": 2,
            "status": "passed",
        }
    except ProviderProbeError:
        raise
    except EmbeddingProviderError as exc:
        raise ProviderProbeError(
            f"embedding probe failed for model {config.model!r} at "
            f"{config.endpoint!r}: {exc}"
        ) from exc
    except Exception as exc:
        raise ProviderProbeError(
            f"embedding probe failed for model {config.model!r} at "
            f"{config.endpoint!r}: {type(exc).__name__}"
        ) from exc
    finally:
        provider.close()


def discover_embedding_dimensions(
    config: EmbeddingApiConfig,
    *,
    token: str,
    client: httpx.Client | None = None,
) -> int:
    """Infer vector width from one real embedding instead of user input."""

    if not token:
        raise ProviderProbeError("embedding token is empty")
    owns_client = client is None
    active = client or httpx.Client(timeout=config.timeout_seconds)
    endpoint = config.endpoint.rstrip("/") + "/embeddings"
    try:
        response = active.post(
            endpoint,
            headers=provider_request_headers(endpoint, token),
            json={"model": config.model, "input": ["LedgerMind dimension probe"]},
            timeout=config.timeout_seconds,
        )
        _safe_status(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderProbeError("embedding response is not JSON") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        embedding = (
            data[0].get("embedding")
            if isinstance(data, list) and data and isinstance(data[0], dict)
            else None
        )
        if (
            not isinstance(embedding, list)
            or not embedding
            or any(not isinstance(value, (int, float)) for value in embedding)
        ):
            raise ProviderProbeError("embedding response has no numeric vector")
        return len(embedding)
    except httpx.TimeoutException as exc:
        raise ProviderProbeError("embedding dimension probe timed out") from exc
    except httpx.RequestError as exc:
        raise ProviderProbeError(
            f"embedding dimension probe failed: {type(exc).__name__}"
        ) from exc
    finally:
        if owns_client:
            active.close()


__all__ = [
    "discover_embedding_dimensions",
    "probe_embedding_api",
    "probe_generation",
]
