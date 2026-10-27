from __future__ import annotations

import pytest

from ledgermind_local.inference.profiles import InferenceProfile
from ledgermind_local.inference.providers.google_boundary import GoogleGenerationTransport
from ledgermind_local.inference.providers.base import (
    ChatMessage,
    ModelRequest,
    ProviderConfigurationError,
)
from ledgermind_local.inference.structured_json_provider import default_provider_factory


def _profile() -> InferenceProfile:
    return InferenceProfile(
        profile_id="google",
        provider_kind="google_genai",
        base_url="https://generativelanguage.googleapis.com",
        model="gemini-test",
        secret_ref="google-secret",
    )


def test_google_boundary_is_explicitly_deferred_and_contract_compatible() -> None:
    transport = default_provider_factory(_profile(), "secret")

    assert isinstance(transport, GoogleGenerationTransport)
    assert transport.provider_kind == "google_genai"
    assert transport.probe_capabilities(_profile())["implemented"] is False
    with pytest.raises(ProviderConfigurationError):
        transport.complete_json(
            ModelRequest(
                model="gemini-test",
                messages=(ChatMessage(role="user", content="return"),),
                max_output_tokens=10,
            )
        )
