from __future__ import annotations

import json

import httpx
import pytest

from ledgermind_local.inference.gguf_vectorizer import GGUFVectorizer
from ledgermind_local.inference.openai_vectorizer import OpenAIEmbeddingVectorizer
from ledgermind_local.inference.vectorizer import VectorizerRoleError
from ledgermind_local.installer.profiles.embedding_api import (
    EmbeddingProviderError,
    EmbeddingProviderTransportError,
    EmbeddingProviderUnavailableError,
    OpenAICompatibleEmbeddingProvider,
)


def _provider(seen: list[dict[str, object]]) -> OpenAICompatibleEmbeddingProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "embed-model",
                "data": [
                    {"index": index, "embedding": [float(index + 1), 0.0]}
                    for index in range(len(json.loads(request.content)["input"]))
                ],
            },
        )

    return OpenAICompatibleEmbeddingProvider(
        endpoint="https://provider.example/v1",
        token="secret",
        model="embed-model",
        dimensions=2,
        batch_size=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize("role", ["query", "passage"])
def test_openai_embedding_wire_preserves_role(role: str) -> None:
    seen: list[dict[str, object]] = []
    provider = _provider(seen)
    try:
        provider.embed(("one", "two"), role=role)  # type: ignore[arg-type]
    finally:
        provider.close()

    assert seen == [
        {
            "model": "embed-model",
            "input": ["one", "two"],
            "input_type": role,
        }
    ]


def test_openrouter_accepts_canonical_model_for_free_routing_variant() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "nvidia/nemotron-3-embed-1b",
                "data": [{"index": 0, "embedding": [1.0, 0.0]}],
            },
        )

    provider = OpenAICompatibleEmbeddingProvider(
        endpoint="https://openrouter.ai/api/v1",
        token="secret",
        model="nvidia/nemotron-3-embed-1b:free",
        dimensions=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        assert provider.embed(("probe",)) == ((1.0, 0.0),)
    finally:
        provider.close()


def test_openrouter_accepts_internal_namespace_for_canonical_model() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "private/openrouter/nvidia/nemotron-3-embed-1b",
                "data": [{"index": 0, "embedding": [1.0, 0.0]}],
            },
        )

    provider = OpenAICompatibleEmbeddingProvider(
        endpoint="https://openrouter.ai/api/v1",
        token="secret",
        model="nvidia/nemotron-3-embed-1b:free",
        dimensions=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        assert provider.embed(("probe",)) == ((1.0, 0.0),)
    finally:
        provider.close()


def test_embedding_provider_still_rejects_a_different_model() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "nvidia/different-embed-model",
                "data": [{"index": 0, "embedding": [1.0, 0.0]}],
            },
        )

    provider = OpenAICompatibleEmbeddingProvider(
        endpoint="https://openrouter.ai/api/v1",
        token="secret",
        model="nvidia/nemotron-3-embed-1b:free",
        dimensions=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(
            RuntimeError,
            match="configured 'nvidia/nemotron-3-embed-1b:free'.*different",
        ):
            provider.embed(("probe",))
    finally:
        provider.close()


@pytest.mark.parametrize("status_code", [408, 409, 425, 429, 500, 503])
def test_embedding_provider_classifies_transient_http_statuses(
    status_code: int,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "retry"}})

    provider = OpenAICompatibleEmbeddingProvider(
        endpoint="https://provider.example/v1",
        token="secret",
        model="embed-model",
        dimensions=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(EmbeddingProviderUnavailableError):
            provider.embed(("probe",))
    finally:
        provider.close()


def test_embedding_provider_keeps_permanent_http_failure_non_retryable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad input"}})

    provider = OpenAICompatibleEmbeddingProvider(
        endpoint="https://provider.example/v1",
        token="secret",
        model="embed-model",
        dimensions=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(EmbeddingProviderError) as raised:
            provider.embed(("probe",))
        assert not isinstance(raised.value, EmbeddingProviderUnavailableError)
    finally:
        provider.close()


def test_embedding_provider_classifies_transport_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    provider = OpenAICompatibleEmbeddingProvider(
        endpoint="https://provider.example/v1",
        token="secret",
        model="embed-model",
        dimensions=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(EmbeddingProviderTransportError):
            provider.embed(("probe",))
    finally:
        provider.close()


def test_openai_vectorizer_keeps_one_role_for_every_batch() -> None:
    seen: list[dict[str, object]] = []
    provider = _provider(seen)
    vectorizer = OpenAIEmbeddingVectorizer(
        endpoint="https://provider.example/v1",
        token="secret",
        model="embed-model",
        dimensions=2,
        batch_size=2,
        timeout_seconds=2,
    )
    # Replace the concrete adapter's HTTP client with the deterministic mock
    # provider used above; the assertion is about the adapter wire boundary.
    vectorizer._provider.close()
    vectorizer._provider = provider
    try:
        vectorizer.encode(("one", "two", "three"), role="query")
    finally:
        vectorizer.close()

    assert [payload["input_type"] for payload in seen] == ["query", "query"]
    assert [payload["input"] for payload in seen] == [["one", "two"], ["three"]]


def test_gguf_rejects_required_role_instead_of_using_plain_embeddings() -> None:
    vectorizer = GGUFVectorizer(
        model_path="/tmp/model.gguf",
        model_builder=lambda *_: pytest.fail("GGUF model must not be opened"),
    )

    with pytest.raises(VectorizerRoleError, match="does not support"):
        vectorizer.encode(("query",), role="query")
