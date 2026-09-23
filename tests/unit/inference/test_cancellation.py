from __future__ import annotations

import threading

import httpx
import pytest

from ledgermind_local.inference.cancellation import CancellationToken
from ledgermind_local.inference.providers.base import (
    ModelRequest,
    ProviderCancelledError,
)
from ledgermind_local.inference.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


def _request() -> ModelRequest:
    return ModelRequest.from_messages(
        model="test-model",
        system_prompt="Return JSON only.",
        user_prompt="Find hypotheses.",
        max_output_tokens=100,
    )


def test_provider_cancellation_before_request_skips_http_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": []})

    token = CancellationToken()
    token.cancel()
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="x",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderCancelledError, match="cancelled") as error:
        provider.complete_json(_request(), token=token)

    assert calls == 0
    assert "x" not in str(error.value)
    provider.close()


def test_provider_cancellation_interrupts_retry_wait() -> None:
    calls = 0
    first_request = threading.Event()
    token = CancellationToken()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        first_request.set()
        return httpx.Response(503)

    def cancel_after_first_request() -> None:
        assert first_request.wait(timeout=1)
        token.cancel()

    canceller = threading.Thread(target=cancel_after_first_request)
    canceller.start()
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="x",
        max_retries=2,
        retry_delay_seconds=10,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderCancelledError):
        provider.complete_json(_request(), cancellation_token=token)

    canceller.join(timeout=1)
    assert not canceller.is_alive()
    assert calls == 1
    provider.close()


def test_provider_uses_independent_http_timeout_phases() -> None:
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="x",
        timeout_seconds=30,
        connect_timeout_seconds=1,
        read_timeout_seconds=2,
        write_timeout_seconds=3,
        pool_timeout_seconds=4,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
    )

    timeout = provider.timeout
    assert timeout.connect == 1
    assert timeout.read == 2
    assert timeout.write == 3
    assert timeout.pool == 4
    provider.close()
