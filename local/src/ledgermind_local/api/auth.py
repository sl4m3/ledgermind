"""Bearer token authentication helpers for local API endpoints."""

from __future__ import annotations

import hmac
from collections.abc import Callable

from fastapi import Header

from .dependencies import Settings
from .errors import AuthenticationError


def build_bearer_token_dependency(
    *,
    settings: Settings,
) -> Callable[[str | None], str]:
    """Return a reusable auth dependency.

    If ``api_token`` is not configured, dependency is effectively disabled.
    """

    if settings.api_token is None:

        def _disabled(_: str | None = None) -> str:
            return ""

        return _disabled

    expected = settings.api_token.encode("utf-8")

    def _require_token(authorization: str | None = Header(default=None)) -> str:
        if authorization is None:
            raise AuthenticationError("missing API token")

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthenticationError("invalid API token format")

        provided = token.encode("utf-8")
        if not hmac.compare_digest(provided, expected):
            raise AuthenticationError("invalid API token")

        return token

    return _require_token


def build_optional_bearer_token_dependency(
    *,
    settings: Settings,
) -> Callable[[str | None], bool]:
    """Return optional auth dependency: returns True only for valid token."""

    required = build_bearer_token_dependency(settings=settings)

    def _optional_token(authorization: str | None = Header(default=None)) -> bool:
        try:
            required(authorization)
            return True
        except AuthenticationError:
            return False

    return _optional_token
