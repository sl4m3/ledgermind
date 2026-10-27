"""Reusable API error types and handlers."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import status
from starlette.requests import Request
from starlette.responses import JSONResponse


class APIError(RuntimeError):
    """Base class for HTTP API domain errors."""


@dataclass(frozen=True, slots=True)
class AuthenticationError(APIError):
    detail: str = "invalid or missing API token"


async def authentication_error_handler(
    _: Request,
    exc: AuthenticationError,
) -> JSONResponse:
    """Convert authentication exceptions to a stable 401 response."""

    payload = {"detail": exc.detail}
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=payload,
        headers={"WWW-Authenticate": "Bearer"},
    )
