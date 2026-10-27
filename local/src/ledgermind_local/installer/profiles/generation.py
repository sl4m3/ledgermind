"""Generation profile construction for all production generation slots."""

from __future__ import annotations

from typing import Any

from ..models import GenerationConfig
from ..provider_profiles import generation_provider_profile
from ..secret_refs import GENERATION_SECRET_REF


def build_generation_profiles(
    config: GenerationConfig,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    provider = generation_provider_profile(config.provider_profile)
    # Reasoning is disabled for every semantic generation role. The selected
    # provider profile owns the wire dialect; URL guessing never changes a
    # production request after installation.
    extra_body: dict[str, Any] = dict(provider.reasoning_extra_body)
    if config.route:
        routes = [config.route, *config.fallback_routes]
        extra_body["provider"] = {
            "order": routes,
            "only": routes,
            "allow_fallbacks": bool(config.fallback_routes),
            "require_parameters": True,
        }
    common = {
        "endpoint": config.endpoint,
        "secret_ref": GENERATION_SECRET_REF,
        "timeout_seconds": config.timeout_seconds,
        "max_concurrency": config.max_concurrency,
        "structured_json_support": config.structured_json_support,
        "provider_kind": provider.provider_kind,
        "provider_profile": provider.profile_id,
        "extra_body": extra_body,
    }
    return (
        {
            "profile_id": "generation-operational",
            "slot": "operational",
            "model": config.model,
            "max_output_tokens": 6_144,
            **common,
        },
        {
            "profile_id": "generation-object-resolution",
            "slot": "object_resolution",
            "model": config.model,
            **common,
        },
        {
            "profile_id": "generation-background",
            "slot": "background",
            "model": config.model,
            **common,
        },
    )


__all__ = ["build_generation_profiles"]
