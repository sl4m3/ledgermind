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
    LedgerMindConflictError,
    LedgerMindNetworkError,
    LedgerMindPermanentError,
    LedgerMindResponseError,
    LedgerMindUnauthorizedError,
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


def test_client_forwards_visibility_and_reports_hook_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    calls: list[tuple[str, dict[str, Any]]] = []

    def request(_method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((path, payload))
        return _response() if path == "/context/retrieve" else {"status": "accepted"}

    monkeypatch.setattr(client, "_request", request)
    client.retrieve_context(memory_space_id="space", query="test", visible_value_ids=["value-1"])
    client.report_injection_event(
        event_id="event-1", retrieval_request_id="retrieval-1",
        memory_space_id="space", session_id="session", stage="hook_returned_assumed_visible",
        value_ids=["value-2"],
    )
    assert calls[0][1]["visible_value_ids"] == ["value-1"]
    assert calls[1][0] == "/context/injection-events"
    assert calls[1][1]["stage"] == "hook_returned_assumed_visible"


def test_client_preserves_explicit_recall_scope(monkeypatch):
    client = _client()
    requests = []
    monkeypatch.setattr(client, "_request", lambda method, path, payload: requests.append(payload) or _response())
    client.retrieve_context(memory_space_id="space", query="continue", project_id="p",
        repository_id="r", conversation_id="c", task_id="t", query_context="Release procedure")
    assert requests[0] == {"memory_space_id": "space", "query": "continue", "limit": 5,
        "project_id": "p", "repository_id": "r", "conversation_id": "c", "task_id": "t",
        "query_context": "Release procedure"}


def test_client_forwards_explicit_retrieval_schema_and_time(monkeypatch):
    client = _client()
    requests = []
    monkeypatch.setattr(client, "_request", lambda method, path, payload: requests.append(payload) or _response())
    client.retrieve_context(
        memory_space_id="space", query="continue", schema_version=5,
        request_time="2026-10-31T12:00:00Z",
    )
    assert requests[0]["schema_version"] == 5
    assert requests[0]["request_time"] == "2026-10-31T12:00:00Z"


def test_client_rejects_unknown_retrieval_schema(monkeypatch):
    client = _client()
    with pytest.raises(ValueError, match="schema_version"):
        client.retrieve_context(memory_space_id="space", query="continue", schema_version=3)


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
    monkeypatch.setattr(client, "_request", lambda *_args: {"status": "unknown"})
    with pytest.raises(LedgerMindResponseError, match="acceptance"):
        client.submit_round({})
    monkeypatch.setattr(
        client, "_request", lambda *_args: {"status": "accepted", "round_id": "round-1"}
    )
    assert client.submit_round({})["round_id"] == "round-1"


def test_empty_successful_rounds_response_confirms_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 204 No Content (empty body) on /rounds is acceptance without a receipt."""

    class Validated:
        def model_dump(self, **_kwargs: Any) -> dict[str, str]:
            return {"idempotency_key": "round-1"}

    from ledgermind_integrations.runtime import client as client_module
    from ledgermind_integrations.runtime.client import round_acceptance_confirmed

    monkeypatch.setattr(client_module, "validate_raw_round", lambda _payload: Validated())
    client = _client()
    monkeypatch.setattr(client, "_request", lambda *_args: {})

    response = client.submit_round({})

    assert round_acceptance_confirmed(response) is True
    # The normalisation is endpoint-specific: an empty mapping never confirms
    # acceptance on its own, and _request keeps returning {} for 204.
    assert round_acceptance_confirmed({}) is False


@pytest.mark.parametrize("status", ["queued_for_core", "retry_wait", "rejected"])
def test_legacy_capture_receipt_is_not_confused_with_core_status(status) -> None:
    from ledgermind_integrations.runtime.client import round_acceptance_confirmed

    receipt = {"schema_version": 2, "raw_round_id": "capture-1", "status": status}
    assert round_acceptance_confirmed(receipt)
    assert not round_acceptance_confirmed({"status": status})
    assert not round_acceptance_confirmed({**receipt, "raw_round_id": ""})
    assert not round_acceptance_confirmed({**receipt, "accepted": False})


def test_rate_limit_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    from ledgermind_integrations.runtime import client as client_module

    def limited(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8765/rounds", 429, "rate limited", {}, BytesIO(b"{}")
        )

    monkeypatch.setattr(client_module.urllib.request, "urlopen", limited)
    with pytest.raises(LedgerMindNetworkError, match="429"):
        _client()._request("POST", "/rounds", {})


@pytest.mark.parametrize("status", [408, 425])
def test_early_or_timeout_status_is_transient(monkeypatch: pytest.MonkeyPatch, status) -> None:
    from ledgermind_integrations.runtime import client as client_module

    def transient(*_args: Any, _status: int = status, **_kwargs: Any) -> Any:
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8765/rounds", _status, "transient", {}, BytesIO(b"{}")
        )

    monkeypatch.setattr(client_module.urllib.request, "urlopen", transient)
    with pytest.raises(LedgerMindNetworkError, match=str(status)):
        _client()._request("POST", "/rounds", {})


def test_204_no_content_is_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NoContent:
        status = 204

        def read(self) -> bytes:
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(
        "ledgermind_integrations.runtime.client.urllib.request.urlopen",
        lambda *_args, **_kwargs: _NoContent(),
    )
    assert _client()._request("POST", "/rounds", {}) == {}


def test_permanent_4xx_raises_permanent_error_with_status() -> None:
    from ledgermind_integrations.runtime import client as client_module

    for code in (400, 403, 404, 413, 422):

        def denied(*_args: Any, _code: int = code, **_kwargs: Any) -> Any:
            raise urllib.error.HTTPError(
                "http://127.0.0.1:8765/rounds", _code, "denied", {}, BytesIO(b"{}")
            )

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(client_module.urllib.request, "urlopen", denied)
        with pytest.raises(LedgerMindPermanentError) as excinfo:
            _client()._request("POST", "/rounds", {})
        assert excinfo.value.status == code
        assert excinfo.value.reason == f"http_{code}"
        monkeypatch.undo()


def test_unauthorized_and_conflict_are_permanent_subclasses() -> None:
    assert issubclass(LedgerMindUnauthorizedError, LedgerMindPermanentError)
    assert issubclass(LedgerMindConflictError, LedgerMindPermanentError)
    unauthorized = LedgerMindUnauthorizedError()
    assert unauthorized.status == 401
    assert unauthorized.reason == "unauthorized"
    conflict = LedgerMindConflictError()
    assert conflict.status == 409
    assert conflict.reason == "source_round_conflict"


def test_invalid_raw_round_raises_permanent_error() -> None:
    client = _client()
    with pytest.raises(LedgerMindPermanentError) as excinfo:
        client.submit_round({"schema_version": 2})
    assert excinfo.value.status == 422
    assert excinfo.value.reason == "invalid_raw_round"


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


def test_runtime_lease_bootstraps_when_foreign_server_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ForeignClient:
        endpoint = "http://127.0.0.1:8765"

        def runtime_acquire(self, **_kwargs: object) -> dict[str, str]:
            # A foreign service on the expected port answers 404; the real client
            # maps that to a permanent error, which must still trigger bootstrap.
            raise LedgerMindPermanentError("server returned 404", status=404, reason="http_404")

        def runtime_heartbeat(self, _lease_id: str) -> dict[str, str]:
            return {}

        def runtime_release(self, _lease_id: str) -> dict[str, str]:
            return {}

    def bootstrap(client: ForeignClient, **_kwargs: object) -> dict[str, str]:
        client.endpoint = "http://127.0.0.1:8767"
        return {"lease_id": "lease-recovered"}

    monkeypatch.setattr(lease_module, "_bootstrap_runtime", bootstrap)
    client = ForeignClient()
    lease = lease_module.RuntimeLease.acquire(
        cast(Any, client),
        client_id="opencode",
        session_id="one",
        heartbeat_seconds=10,
        bootstrap_command="ledgermind",
        start_heartbeat=False,
    )
    assert lease.lease_id == "lease-recovered"
    assert client.endpoint == "http://127.0.0.1:8767"


def test_cold_runtime_bootstraps_without_contacting_occupied_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ColdClient:
        endpoint = "http://127.0.0.1:8765"

        def runtime_acquire(self, **_kwargs: object) -> dict[str, str]:
            raise AssertionError("cold start must not send a token to another service")

    monkeypatch.setattr(
        lease_module,
        "_bootstrap_runtime",
        lambda _client, **_kwargs: {"lease_id": "lease-safe"},
    )
    lease = lease_module.RuntimeLease.acquire(
        cast(Any, ColdClient()),
        client_id="opencode",
        session_id="one",
        heartbeat_seconds=10,
        bootstrap_command="ledgermind",
        start_heartbeat=False,
        prefer_bootstrap=True,
    )
    assert lease.lease_id == "lease-safe"


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
