"""Explicit installer-owned generation provider profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GenerationProviderProfileId = Literal[
    "openrouter",
    "nvidia_nim",
    "openai_compatible",
]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]
_EFFORT_VALUES = ("none", "minimal", "low", "medium", "high")


@dataclass(frozen=True, slots=True)
class GenerationProviderProfile:
    profile_id: GenerationProviderProfileId
    label: str
    default_endpoint: str | None
    provider_kind: Literal["openai_compatible", "nvidia_nim"]
    reasoning_extra_body: dict[str, object]


_PROFILES: dict[GenerationProviderProfileId, GenerationProviderProfile] = {
    "openrouter": GenerationProviderProfile(
        profile_id="openrouter",
        label="OpenRouter",
        default_endpoint="https://openrouter.ai/api/v1",
        provider_kind="openai_compatible",
        reasoning_extra_body={
            "reasoning": {"effort": "none", "exclude": True},
        },
    ),
    "nvidia_nim": GenerationProviderProfile(
        profile_id="nvidia_nim",
        label="NVIDIA NIM",
        default_endpoint="https://integrate.api.nvidia.com/v1",
        provider_kind="nvidia_nim",
        reasoning_extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
        },
    ),
    "openai_compatible": GenerationProviderProfile(
        profile_id="openai_compatible",
        label="Custom OpenAI-compatible",
        default_endpoint=None,
        provider_kind="openai_compatible",
        reasoning_extra_body={"reasoning_effort": "none"},
    ),
}


def generation_provider_profile(
    profile_id: GenerationProviderProfileId,
) -> GenerationProviderProfile:
    return _PROFILES[profile_id]


def infer_generation_provider_profile(endpoint: str) -> GenerationProviderProfileId:
    normalized = endpoint.strip().lower()
    if "openrouter.ai" in normalized:
        return "openrouter"
    if "integrate.api.nvidia.com" in normalized:
        return "nvidia_nim"
    return "openai_compatible"


def generation_provider_profiles() -> tuple[GenerationProviderProfile, ...]:
    return tuple(_PROFILES.values())


def normalize_reasoning_effort(value: object) -> ReasoningEffort | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in _EFFORT_VALUES:
        return normalized  # type: ignore[return-value]
    return None


def reasoning_extra_body_for(
    profile_id: GenerationProviderProfileId,
    *,
    reasoning_effort: str | None = None,
) -> dict[str, object]:
    """Build provider-specific reasoning controls for one generation slot."""

    effort = normalize_reasoning_effort(reasoning_effort) or "none"
    if profile_id == "openrouter":
        return {"reasoning": {"effort": effort, "exclude": True}}
    if profile_id == "nvidia_nim":
        return {"chat_template_kwargs": {"enable_thinking": effort != "none"}}
    return {"reasoning_effort": effort}


__all__ = [
    "GenerationProviderProfile",
    "GenerationProviderProfileId",
    "ReasoningEffort",
    "generation_provider_profile",
    "generation_provider_profiles",
    "infer_generation_provider_profile",
    "normalize_reasoning_effort",
    "reasoning_extra_body_for",
]
