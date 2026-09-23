from __future__ import annotations

import pytest

from ledgermind_local.installer.models import GenerationConfig
from ledgermind_local.installer.profiles.generation import build_generation_profiles


def _generation_config(
    *,
    endpoint: str,
    route: str | None = None,
    fallback_routes: tuple[str, ...] = (),
) -> GenerationConfig:
    return GenerationConfig(
        endpoint=endpoint,
        route=route,
        fallback_routes=fallback_routes,
        token="test-token",
        model="deepseek/deepseek-v4-flash-0731",
        object_resolution_model="deepseek/deepseek-v4-flash-0731",
    )


def test_openrouter_runtime_matches_probe_reasoning_and_route_controls() -> None:
    profiles = build_generation_profiles(
        _generation_config(
            endpoint="https://openrouter.ai/api/v1",
            route="baidu/fp8",
            fallback_routes=("deepinfra/fp8",),
        )
    )

    for profile in profiles:
        assert profile["extra_body"] == {
            "reasoning": {"effort": "none", "exclude": True},
            "provider": {
                "order": ["baidu/fp8", "deepinfra/fp8"],
                "only": ["baidu/fp8", "deepinfra/fp8"],
                "allow_fallbacks": True,
                "require_parameters": True,
            },
        }

    by_slot = {profile["slot"]: profile for profile in profiles}
    assert by_slot["operational"]["max_output_tokens"] == 6_144
    assert "max_output_tokens" not in by_slot["object_resolution"]
    assert "max_output_tokens" not in by_slot["background"]


def test_openrouter_single_route_remains_strictly_pinned() -> None:
    profiles = build_generation_profiles(
        _generation_config(
            endpoint="https://openrouter.ai/api/v1",
            route="baidu/fp8",
        )
    )

    assert all(
        profile["extra_body"]["provider"]
        == {
            "order": ["baidu/fp8"],
            "only": ["baidu/fp8"],
            "allow_fallbacks": False,
            "require_parameters": True,
        }
        for profile in profiles
    )


def test_openrouter_rejects_more_than_one_fallback_route() -> None:
    with pytest.raises(ValueError, match="at most one fallback route"):
        _generation_config(
            endpoint="https://openrouter.ai/api/v1",
            route="primary/fp8",
            fallback_routes=("fallback-a/fp8", "fallback-b/fp8"),
        )


def test_generic_runtime_disables_reasoning_with_openai_compatible_control() -> None:
    profiles = build_generation_profiles(
        _generation_config(endpoint="https://provider.example/v1")
    )

    assert all(
        profile["extra_body"] == {"reasoning_effort": "none"} for profile in profiles
    )


def test_nvidia_runtime_uses_native_profile_and_disables_thinking() -> None:
    profiles = build_generation_profiles(
        GenerationConfig(
            provider_profile="nvidia_nim",
            endpoint="https://integrate.api.nvidia.com/v1",
            token="test-token",
            model="nvidia/nemotron-3-super-120b-a12b",
            object_resolution_model="nvidia/nemotron-3-super-120b-a12b",
        )
    )

    assert all(profile["provider_kind"] == "nvidia_nim" for profile in profiles)
    assert all(
        profile["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
        for profile in profiles
    )
