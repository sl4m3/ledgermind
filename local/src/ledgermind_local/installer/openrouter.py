"""OpenRouter endpoint discovery for the interactive installer.

Discovery only narrows the menu.  The installer still performs a real strict
JSON Schema request against the selected route before changing the host.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import httpx

from ..inference.providers.openai_compatible import provider_request_headers
from .errors import ProviderProbeError


@dataclass(frozen=True, slots=True)
class OpenRouterEndpoint:
    route: str
    provider: str
    quantization: str | None
    context_length: int | None
    prompt_price: str | None
    completion_price: str | None
    supported_parameters: tuple[str, ...]

    @property
    def label(self) -> str:
        quantization = f" / {self.quantization}" if self.quantization else ""
        return f"{self.provider}{quantization}"

    @property
    def detail(self) -> str:
        parts: list[str] = []
        if self.context_length:
            parts.append(f"{self.context_length:,} context")
        if self.prompt_price is not None and self.completion_price is not None:
            parts.append(
                "input "
                f"{_per_million(self.prompt_price)} / 1M; output "
                f"{_per_million(self.completion_price)} / 1M"
            )
        return ", ".join(parts)


def _per_million(value: str) -> str:
    try:
        amount = Decimal(value) * Decimal(1_000_000)
    except InvalidOperation:
        return "unknown"
    rendered = f"{amount:.6f}".rstrip("0").rstrip(".")
    if "." not in rendered:
        rendered += ".00"
    elif len(rendered.rsplit(".", 1)[1]) == 1:
        rendered += "0"
    return f"${rendered}"


def _route_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug


def _endpoint_route(payload: dict[str, Any]) -> tuple[str, str] | None:
    provider = next(
        (
            value.strip()
            for key in ("provider_name", "provider", "name")
            if isinstance((value := payload.get(key)), str) and value.strip()
        ),
        None,
    )
    if provider is None:
        return None
    provider = provider.split("|")[0].strip()
    provider_slug = _route_slug(provider)
    if not provider_slug:
        return None
    quantization = payload.get("quantization")
    quantization_slug = (
        _route_slug(quantization) if isinstance(quantization, str) else ""
    )
    route = provider_slug
    if quantization_slug and quantization_slug not in {"unknown", "other"}:
        route += f"/{quantization_slug}"
    return route, provider


def list_openrouter_model_endpoints(
    model: str,
    *,
    token: str,
    client: httpx.Client | None = None,
    timeout_seconds: float = 30.0,
) -> tuple[OpenRouterEndpoint, ...]:
    """Return endpoints advertising strict structured-output transport."""

    if not token.strip():
        raise ProviderProbeError("OpenRouter token is empty")
    if "/" not in model:
        raise ProviderProbeError("OpenRouter model must use author/model form")
    author, slug = model.split("/", 1)
    url = (
        "https://openrouter.ai/api/v1/models/"
        f"{quote(author, safe='')}/{quote(slug, safe='')}/endpoints"
    )
    owns_client = client is None
    active = client or httpx.Client(timeout=timeout_seconds)
    try:
        response = active.get(
            url,
            headers=provider_request_headers("https://openrouter.ai/api/v1", token),
            timeout=timeout_seconds,
        )
        if response.status_code in {401, 403}:
            raise ProviderProbeError("OpenRouter authentication failed")
        if response.status_code == 404:
            raise ProviderProbeError(f"OpenRouter model {model!r} was not found")
        if response.status_code >= 400:
            raise ProviderProbeError(
                f"OpenRouter endpoint discovery returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderProbeError(
                "OpenRouter endpoint discovery returned invalid JSON"
            ) from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        raw_endpoints = data.get("endpoints") if isinstance(data, dict) else None
        if not isinstance(raw_endpoints, list):
            raise ProviderProbeError(
                "OpenRouter endpoint discovery returned no endpoints"
            )
        endpoints: list[OpenRouterEndpoint] = []
        seen: set[str] = set()
        for item in raw_endpoints:
            if not isinstance(item, dict):
                continue
            supported_raw = item.get("supported_parameters")
            supported = (
                tuple(str(value) for value in supported_raw if isinstance(value, str))
                if isinstance(supported_raw, list)
                else ()
            )
            # OpenRouter exposes strict JSON Schema through structured_outputs;
            # response_format confirms that the endpoint accepts the transport.
            if not {"structured_outputs", "response_format"}.issubset(supported):
                continue
            resolved = _endpoint_route(item)
            if resolved is None:
                continue
            route, provider = resolved
            if route in seen:
                continue
            seen.add(route)
            pricing = item.get("pricing")
            if not isinstance(pricing, dict):
                pricing = {}
            context_length = item.get("context_length")
            endpoints.append(
                OpenRouterEndpoint(
                    route=route,
                    provider=provider,
                    quantization=(
                        item.get("quantization")
                        if isinstance(item.get("quantization"), str)
                        else None
                    ),
                    context_length=(
                        context_length if isinstance(context_length, int) else None
                    ),
                    prompt_price=(
                        str(pricing["prompt"])
                        if pricing.get("prompt") is not None
                        else None
                    ),
                    completion_price=(
                        str(pricing["completion"])
                        if pricing.get("completion") is not None
                        else None
                    ),
                    supported_parameters=supported,
                )
            )
        if not endpoints:
            raise ProviderProbeError(
                f"OpenRouter has no endpoints advertising strict JSON Schema for {model!r}"
            )
        return tuple(endpoints)
    except httpx.TimeoutException as exc:
        raise ProviderProbeError("OpenRouter endpoint discovery timed out") from exc
    except httpx.RequestError as exc:
        raise ProviderProbeError(
            f"OpenRouter endpoint discovery failed: {type(exc).__name__}"
        ) from exc
    finally:
        if owns_client:
            active.close()


__all__ = ["OpenRouterEndpoint", "list_openrouter_model_endpoints"]
