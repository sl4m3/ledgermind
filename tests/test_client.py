from __future__ import annotations

import json
import subprocess
import urllib.error
from io import BytesIO
from typing import Any, cast

import pytest

import ledgermind_integrations
from ledgermind_integrations.runtime import lease as lease_module
from ledgermind_integrations.runtime.client import (
    LedgerMindClient,
    LedgerMindNetworkError,
    LedgerMindResponseError,
)


def _client() -> LedgerMindClient:
    return LedgerMindClient(endpoint="http://127.0.0.1:8765")


def _response() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "retrieval_request_id": "retrieval-1",
        "delivered_value_ids": ["value-1"],
        "items": [
            {
                "value_id": "value-1",
                "primary_object_id": "object-1",
                "object_name": "Repository",
                "facet": "property",
                "content": "Use the public protocol.",
                "source_event_ids": ["event-1"],
                "relevance": 0.9,
                "explanation": {
                    "object_reasons": ["direct_value_semantic"],
                    "item_facet": "property",
                    "activated_facets": [],
                    "score_components": {
                        "semantic_similarity": 0.9,
                        "semantic_contribution": 0.9,
                        "object_similarity": 0.0,
                        "object_contribution": 0.0,
                        "facet_compatibility": 0.0,
                        "facet_contribution": 0.0,
                        "scope_time_compatibility": 0.0,
                        "scope_time_contribution": 0.0,
                        "context_compatibility": 0.0,
                        "context_contribution": 0.0,
                        "recency_component": 0.0,
                        "recency_contribution": 0.0,
                        "support_component": 0.0,
                        "support_contribution": 0.0,
                        "usage_component": 0.0,
                        "usage_contribution": 0.0,
                        "final_score": 0.9,
                    },
                },
            }
        ],
    }


def test_integration_package_exports_client_boundary() -> None:
    assert "LedgerMindClient" in ledgermind_integrations.__all__
    assert ledgermind_integrations.LedgerMindClient is LedgerMindClient


def test_client_returns_strict_context_view(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    requests: list[dict[str, Any]] = []

    def request(_method: str, _path: str, payload: dict[str, Any]) -> dict[str, Any]:
        requests.append(payload)
        return _response()

    monkeypatch.setattr(client, "_request", request)

    response = client.retrieve_context(memory_space_id="space-1", query="protocol")

    assert response["retrieval_request_id"] == "retrieval-1"
    assert response["items"][0]["value_id"] == "value-1"
    assert requests == [{"memory_space_id": "space-1", "query": "protocol", "limit": 5}]


def test_client_uses_stable_http_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    paths: list[str] = []

    def request(_method: str, path: str, _payload: dict[str, Any] | None) -> dict[str, Any]:
        paths.append(path)
        return {}

    monkeypatch.setattr(client, "_request", request)

    client.ping()
    client.health_live()
    client.health_capture_ready()
    client.health_full_ready()
    client.health()
    client.health_details()

    assert paths == [
        "/ping",
        "/health/live",
        "/health/capture-ready",
        "/health/full-ready",
        "/health/ready",
        "/health/details",
    ]


def test_client_rejects_legacy_context_item_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    legacy = {"items": [{"knowledge_id": "k1", "title": "old", "statement": "old"}]}
    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: legacy)

    with pytest.raises(LedgerMindResponseError, match="ContextView"):
        client.retrieve_context(memory_space_id="space-1", query="protocol")


def test_submit_round_requires_explicit_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    class Validated:
        def model_dump(self, **_kwargs: Any) -> dict[str, str]:
            return {"idempotency_key": "round-1"}

    from ledgermind_integrations.runtime import client as client_module

    monkeypatch.setattr(client_module, "validate_raw_round", lambda _payload: Validated())
    client = _client()
    monkeypatch.setattr(client, "_request", lambda *_args: {})
    with pytest.raises(LedgerMindResponseError, match="acceptance"):
        client.submit_round({})
    monkeypatch.setattr(
        client, "_request", lambda *_args: {"status": "accepted", "round_id": "round-1"}
    )
    assert client.submit_round({})["round_id"] == "round-1"


def test_rate_limit_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    from ledgermind_integrations.runtime import client as client_module

    def limited(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8765/rounds", 429, "rate limited", {}, BytesIO(b"{}")
        )

    monkeypatch.setattr(client_module.urllib.request, "urlopen", limited)
    with pytest.raises(LedgerMindNetworkError, match="429"):
        _client()._request("POST", "/rounds", {})


def test_runtime_bootstrap_updates_endpoint_and_waits_for_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        endpoint = "http://127.0.0.1:8765"
        timeout = 0.1

        def health_live(self) -> dict[str, Any]:
            return {"status": "ok"}

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command[-7:] == [
            "runtime",
            "acquire",
            "--client",
            "hermes",
            "--session-id",
            "session-1",
            "--json",
        ]
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 45.0
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "runtime": {
                        "lease_id": "lease-1",
                        "endpoint": "http://127.0.0.1:8766",
                    }
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(lease_module.subprocess, "run", run)
    result = lease_module._bootstrap_runtime(
        cast(Any, FakeClient()),
        client_id="hermes",
        session_id="session-1",
        command="ledgermind",
    )

    assert result["lease_id"] == "lease-1"


def test_runtime_bootstrap_releases_lease_when_service_never_becomes_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        endpoint = "http://127.0.0.1:8765"
        timeout = 0.1

        def health_live(self) -> dict[str, Any]:
            raise LedgerMindNetworkError("offline")

    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "acquire" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "runtime": {
                            "lease_id": "lease-orphan",
                            "endpoint": "http://127.0.0.1:8766",
                        }
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    ticks = iter((0.0, 0.0, 6.0))
    monkeypatch.setattr(lease_module.subprocess, "run", run)
    monkeypatch.setattr(lease_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(lease_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="did not become ready"):
        lease_module._bootstrap_runtime(
            cast(Any, FakeClient()),
            client_id="codex",
            session_id="session-1",
            command="ledgermind",
        )

    assert len(commands) == 2
    assert commands[1][-5:] == [
        "runtime",
        "release",
        "--lease-id",
        "lease-orphan",
        "--json",
    ]
