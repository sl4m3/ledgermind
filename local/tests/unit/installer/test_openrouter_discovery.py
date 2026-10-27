from __future__ import annotations

import httpx
import pytest

from ledgermind_local.installer.errors import ProviderProbeError
from ledgermind_local.installer.openrouter import list_openrouter_model_endpoints

MODEL = "deepseek/deepseek-v4-flash-0731"


def test_openrouter_discovery_keeps_only_strict_schema_endpoints() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/models/{MODEL}/endpoints")
        return httpx.Response(
            200,
            json={
                "data": {
                    "endpoints": [
                        {
                            "provider_name": "Baidu",
                            "quantization": "FP8",
                            "context_length": 163840,
                            "supported_parameters": [
                                "response_format",
                                "structured_outputs",
                            ],
                            "pricing": {
                                "prompt": "0.0000002",
                                "completion": "0.0000004",
                            },
                        },
                        {
                            "provider_name": "Unsafe",
                            "quantization": "FP8",
                            "supported_parameters": ["response_format"],
                        },
                    ]
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        endpoints = list_openrouter_model_endpoints(
            MODEL, token="secret", client=client
        )

    assert [endpoint.route for endpoint in endpoints] == ["baidu/fp8"]
    assert endpoints[0].context_length == 163840
    assert "input $0.20 / 1M; output $0.40 / 1M" in endpoints[0].detail
    assert "per token" not in endpoints[0].detail


def test_openrouter_discovery_reports_no_strict_endpoints() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"endpoints": []}})

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProviderProbeError, match="no endpoints advertising"),
    ):
        list_openrouter_model_endpoints("author/model", token="secret", client=client)
