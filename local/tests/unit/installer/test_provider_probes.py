from __future__ import annotations

import json

import httpx
import pytest

from ledgermind_local.installer.errors import ProviderProbeError
from ledgermind_local.installer.models import EmbeddingApiConfig, GenerationConfig
from ledgermind_local.installer.profiles.probes import (
    discover_embedding_dimensions,
    probe_embedding_api,
    probe_generation,
)


def _config() -> GenerationConfig:
    return GenerationConfig(
        endpoint="https://provider.example/v1",
        token="secret",
        model="strict-model",
    )


def test_installer_generation_probe_uses_strict_schema_and_verifies_shape() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "strict-model",
                "choices": [
                    {
                        "message": {
                            "content": '{"schema_version":1,"state":"ok","items":[1]}'
                        }
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe_generation(_config(), token="secret", client=client)

    assert seen["response_format"]["type"] == "json_schema"  # type: ignore[index]
    assert seen["max_tokens"] == 256
    schema = seen["response_format"]["json_schema"]["schema"]  # type: ignore[index]
    assert schema["additionalProperties"] is False  # type: ignore[index]
    assert schema["properties"]["state"]["enum"] == ["ok"]  # type: ignore[index]
    assert schema["properties"]["items"]["minItems"] == 1  # type: ignore[index]
    assert result["strict_structured_outputs"] is True
    assert result["schema_profile_version"] == "ledgermind-strict-schema"


def test_openrouter_generation_probe_disables_reasoning() -> None:
    seen: dict[str, object] = {}
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen_headers.update(
            {key.lower(): value for key, value in request.headers.items()}
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"schema_version":1,"state":"ok","items":[1]}'
                        }
                    }
                ]
            },
        )

    config = _config().model_copy(
        update={
            "provider_profile": "openrouter",
            "endpoint": "https://openrouter.ai/api/v1",
            "route": "baidu/fp8",
            "fallback_routes": ("deepinfra/fp8",),
        }
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe_generation(config, token="secret", client=client)

    assert seen["reasoning"] == {"effort": "none", "exclude": True}
    assert seen_headers["http-referer"] == "https://ledgermind.org"
    assert seen_headers["x-title"] == "LedgerMind"
    assert seen["provider"] == {
        "order": ["baidu/fp8", "deepinfra/fp8"],
        "only": ["baidu/fp8", "deepinfra/fp8"],
        "allow_fallbacks": True,
        "require_parameters": True,
    }


def test_generic_generation_probe_disables_reasoning() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"schema_version":1,"state":"ok","items":[1]}'
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe_generation(_config(), token="secret", client=client)

    assert seen["reasoning_effort"] == "none"


def test_nvidia_generation_probe_uses_guided_json_and_disables_thinking() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"schema_version":1,"state":"ok","items":[1]}'
                        }
                    }
                ]
            },
        )

    config = _config().model_copy(
        update={
            "provider_profile": "nvidia_nim",
            "endpoint": "https://integrate.api.nvidia.com/v1",
        }
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        probe_generation(config, token="secret", client=client)

    assert "response_format" not in seen
    guided_json = seen["guided_json"]
    assert isinstance(guided_json, dict)
    assert guided_json["additionalProperties"] is False
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}


def test_generation_probe_explains_empty_reasoning_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": None},
                        "finish_reason": "length",
                        "native_finish_reason": "MAX_TOKENS",
                    }
                ],
                "usage": {
                    "completion_tokens": 32,
                    "completion_tokens_details": {"reasoning_tokens": 32},
                },
            },
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProviderProbeError) as captured,
    ):
        probe_generation(_config(), token="secret", client=client)

    message = str(captured.value)
    assert "finish_reason='length'" in message
    assert "native_finish_reason='MAX_TOKENS'" in message
    assert "completion_tokens=32" in message
    assert "reasoning_tokens=32" in message


def test_installer_generation_probe_rejects_parseable_but_wrong_shape() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok":true}'}}]},
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProviderProbeError, match="strict probe schema"),
    ):
        probe_generation(_config(), token="secret", client=client)


def test_embedding_probe_reports_provider_message_model_and_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://openrouter.ai/api/v1/embeddings"
        return httpx.Response(
            404,
            json={"error": {"message": "No endpoints found for this model"}},
        )

    config = EmbeddingApiConfig(
        endpoint="https://openrouter.ai/api/v1/embeddings",
        token="secret",
        model="missing/embed-model",
        dimensions=2048,
    )
    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProviderProbeError) as captured,
    ):
        probe_embedding_api(config, token="secret", client=client)

    message = str(captured.value)
    assert "missing/embed-model" in message
    assert "https://openrouter.ai/api/v1" in message
    assert "HTTP 404" in message
    assert "No endpoints found for this model" in message


def test_embedding_dimensions_are_inferred_from_real_vector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/embeddings")
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3, 0.4]}]},
        )

    config = EmbeddingApiConfig(
        endpoint="https://provider.example/v1",
        token="secret",
        model="embedding-model",
        dimensions=1,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        dimensions = discover_embedding_dimensions(
            config, token="secret", client=client
        )

    assert dimensions == 4
