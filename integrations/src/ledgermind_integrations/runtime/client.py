"""Dependency-free Local/Cloud HTTP transport for RawRound clients."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ledgermind_protocol import ContextView, validate_raw_round
from ledgermind_protocol.validation import RawRoundValidationError
from pydantic import ValidationError


class LedgerMindClientError(RuntimeError):
    """Base transport error."""


class LedgerMindNetworkError(LedgerMindClientError):
    """Temporary transport or 5xx error.

    Transient failures (408, 425, 429, 5xx, connection reset, timeout, malformed
    JSON) mean the request may still succeed later: callers must keep the round
    queued and retry without a ceiling until the server confirms acceptance.
    """


class LedgerMindPermanentError(LedgerMindClientError):
    """Client-side failure that retrying cannot fix.

    Non-2xx 4xx responses and invalid request envelopes belong here: the request
    is rejected regardless of transport. Callers quarantine these deliveries so
    they neither block the queue nor get lost, typically with ``retryable=True``.
    """

    def __init__(self, message: str, *, status: int = 0, reason: str = "") -> None:
        super().__init__(message)
        self.status = int(status)
        self.reason = reason


class LedgerMindUnauthorizedError(LedgerMindPermanentError):
    """The configured token was rejected (HTTP 401)."""

    def __init__(self, message: str = "authentication failed", *, status: int = 401) -> None:
        super().__init__(message, status=status, reason="unauthorized")


class LedgerMindConflictError(LedgerMindPermanentError):
    """The server rejected a source-round payload conflict (HTTP 409)."""

    def __init__(self, message: str = "raw round conflict", *, status: int = 409) -> None:
        super().__init__(message, status=status, reason="source_round_conflict")


class LedgerMindResponseError(LedgerMindClientError):
    """Protocol or response error from a reachable server.

    Treated as server-side/transient: e.g. malformed JSON or an acknowledgement
    that does not confirm acceptance. Callers keep the round queued and retry.
    """


def round_acceptance_confirmed(response: Mapping[str, Any]) -> bool:
    """Confirm durable capture, independently of subsequent Core processing.

    Older Local servers return a capture receipt with a processing status,
    rather than ``accepted=True``. Never infer acceptance from HTTP 2xx alone.
    """
    if response.get("accepted") is False:
        return False
    if response.get("accepted") is True or response.get("status") == "accepted":
        return True
    return (
        response.get("schema_version") == 2
        and isinstance(response.get("raw_round_id"), str)
        and bool(response["raw_round_id"].strip())
        and response.get("status") in {"queued_for_core", "retry_wait", "rejected"}
    )


def _read_token(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _validate_url(url: str, *, allow_remote: bool) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("endpoint must be an http(s) URL with a host")
    if not allow_remote and parsed.hostname.lower() not in {
        "localhost",
        "127.0.0.1",
        "::1",
        "[::1]",
    }:
        raise ValueError("remote endpoint requires allow_remote=True")
    return url.rstrip("/")


class LedgerMindClient:
    def __init__(
        self,
        *,
        endpoint: str,
        token_file: str | Path | None = None,
        timeout: float = 5.0,
        allow_remote: bool = False,
    ) -> None:
        self.endpoint = _validate_url(endpoint, allow_remote=allow_remote)
        self.token_file = Path(token_file).expanduser() if token_file else None
        self.timeout = max(float(timeout), 0.1)
        self._token = _read_token(self.token_file) if self.token_file else None

    def retrieve_context(
        self, *, memory_space_id: str, query: str, limit: int = 5,
        project_id: str | None = None, repository_id: str | None = None,
        task_id: str | None = None, conversation_id: str | None = None,
        query_context: str | None = None,
        schema_version: int | None = None,
        request_time: str | None = None,
        visible_value_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if schema_version is not None and schema_version not in {2, 4, 5}:
            raise ValueError("schema_version must be 2, 4 or 5")
        payload = self._request(
            "POST",
            "/context/retrieve",
            {
                "memory_space_id": memory_space_id,
                "query": query,
                "limit": int(limit),
                **({"visible_value_ids": visible_value_ids} if visible_value_ids else {}),
                **{key: value for key, value in {
                    "project_id": project_id, "repository_id": repository_id,
                    "task_id": task_id, "conversation_id": conversation_id,
                    "query_context": query_context,
                    "schema_version": schema_version,
                    "request_time": request_time,
                }.items() if value is not None},
            },
        )
        try:
            return ContextView.model_validate(payload).model_dump(mode="json")
        except (TypeError, ValueError, ValidationError) as exc:
            raise LedgerMindResponseError("context response was not ContextView") from exc

    def submit_round(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            validated = validate_raw_round(payload)
        except RawRoundValidationError as exc:
            raise LedgerMindPermanentError(
                "raw round payload was not valid",
                status=422,
                reason="invalid_raw_round",
            ) from exc
        response = self._request(
            "POST",
            "/rounds",
            validated.model_dump(mode="json", exclude_none=True),
        )
        if not response:
            # 204 No Content (and an empty body on 200/201/202) is a successful
            # round submission without a receipt: /rounds confirmed capture at
            # the transport level. Normalised here, for this endpoint only:
            # _request stays generic and round_acceptance_confirmed still never
            # infers acceptance from an empty payload.
            return {"accepted": True}
        if not round_acceptance_confirmed(response):
            raise LedgerMindResponseError("round acceptance was not confirmed")
        return response

    def report_injection_event(
        self, *, event_id: str, retrieval_request_id: str, memory_space_id: str,
        session_id: str, stage: str, value_ids: list[str],
    ) -> dict[str, Any]:
        return self._request("POST", "/context/injection-events", {
            "event_id": event_id, "retrieval_request_id": retrieval_request_id,
            "memory_space_id": memory_space_id, "session_id": session_id,
            "stage": stage, "value_ids": value_ids,
        })

    def ping(self) -> dict[str, Any]:
        return self._request("GET", "/ping", None)

    def health_live(self) -> dict[str, Any]:
        return self._request("GET", "/health/live", None)

    def health_capture_ready(self) -> dict[str, Any]:
        return self._request("GET", "/health/capture-ready", None)

    def health_full_ready(self) -> dict[str, Any]:
        return self._request("GET", "/health/full-ready", None)

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health/ready", None)

    def health_details(self) -> dict[str, Any]:
        return self._request("GET", "/health/details", None)

    def runtime_acquire(
        self,
        *,
        client: str,
        session_id: str,
        ttl_seconds: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"client": client, "session_id": session_id}
        if ttl_seconds is not None:
            payload["ttl_seconds"] = ttl_seconds
        return self._request(
            "POST",
            "/runtime/acquire",
            payload,
        )

    def runtime_heartbeat(self, lease_id: str) -> dict[str, Any]:
        return self._request("POST", "/runtime/heartbeat", {"lease_id": lease_id})

    def runtime_release(self, lease_id: str) -> dict[str, Any]:
        return self._request("POST", "/runtime/release", {"lease_id": lease_id})

    def runtime_status(self) -> dict[str, Any]:
        return self._request("GET", "/runtime/status", None)

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        if self.token_file is not None:
            self._token = _read_token(self.token_file)
        body = (
            None
            if payload is None
            else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        )
        headers = {"accept": "application/json"}
        if body is not None:
            headers["content-type"] = "application/json"
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(
            self.endpoint + path,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            status = exc.code
            if status == 401:
                raise LedgerMindUnauthorizedError("authentication failed") from exc
            if status == 409:
                raise LedgerMindConflictError("raw round conflict") from exc
            if status in {408, 425, 429} or status >= 500:
                # 408 (timeout), 425 (too early) and 429 are transient: the
                # request may succeed later, so keep the round queued and retry.
                raise LedgerMindNetworkError(f"server returned {status}") from exc
            if 400 <= status < 500:
                raise LedgerMindPermanentError(
                    f"server returned {status}: {raw[:500]}",
                    status=status,
                    reason=f"http_{status}",
                ) from exc
            raise LedgerMindResponseError(f"server returned {status}: {raw[:500]}") from exc
        except OSError as exc:
            raise LedgerMindNetworkError(str(exc)) from exc
        if status == 204:
            # 204 No Content is a successful response without a body.
            return {}
        if status not in {200, 201, 202}:
            raise LedgerMindPermanentError(
                f"unexpected status {status}", status=status, reason=f"http_{status}"
            )
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerMindResponseError("response was not JSON") from exc
        if not isinstance(data, dict):
            raise LedgerMindResponseError("response must be a JSON object")
        return data
