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
from pydantic import ValidationError


class LedgerMindClientError(RuntimeError):
    """Base transport error."""


class LedgerMindNetworkError(LedgerMindClientError):
    """Temporary transport or 5xx error."""


class LedgerMindUnauthorizedError(LedgerMindClientError):
    """The configured token was rejected."""


class LedgerMindConflictError(LedgerMindClientError):
    """The server rejected a source-round payload conflict."""


class LedgerMindResponseError(LedgerMindClientError):
    """Non-retriable protocol or response error."""


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
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/context/retrieve",
            {
                "memory_space_id": memory_space_id,
                "query": query,
                "limit": int(limit),
                **{key: value for key, value in {
                    "project_id": project_id, "repository_id": repository_id,
                    "task_id": task_id, "conversation_id": conversation_id,
                    "query_context": query_context,
                }.items() if value is not None},
            },
        )
        try:
            return ContextView.model_validate(payload).model_dump(mode="json")
        except (TypeError, ValueError, ValidationError) as exc:
            raise LedgerMindResponseError("context response was not ContextView") from exc

    def submit_round(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        validated = validate_raw_round(payload)
        response = self._request(
            "POST",
            "/rounds",
            validated.model_dump(mode="json", exclude_none=True),
        )
        if response.get("status") != "accepted" and response.get("accepted") is not True:
            raise LedgerMindResponseError("round acceptance was not confirmed")
        return response

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
            if status == 429 or status >= 500:
                raise LedgerMindNetworkError(f"server returned {status}") from exc
            raise LedgerMindResponseError(f"server returned {status}: {raw[:500]}") from exc
        except OSError as exc:
            raise LedgerMindNetworkError(str(exc)) from exc
        if status not in {200, 201, 202}:
            raise LedgerMindResponseError(f"unexpected status {status}")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerMindResponseError("response was not JSON") from exc
        if not isinstance(data, dict):
            raise LedgerMindResponseError("response must be a JSON object")
        return data
