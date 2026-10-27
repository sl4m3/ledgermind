"""Runtime endpoint contract."""

from __future__ import annotations

from urllib.parse import urlparse


def validate_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("runtime endpoint must be an absolute http(s) URL")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1", "[::1]"}:
        raise ValueError("runtime endpoint must be local")
    return normalized


DEFAULT_ENDPOINT = "http://127.0.0.1:8765"


__all__ = ["DEFAULT_ENDPOINT", "validate_endpoint"]
