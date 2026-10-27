"""Reusable API error types and handlers."""

from __future__ import annotations

from fastapi import status
from starlette.requests import Request
from starlette.responses import JSONResponse


class APIError(RuntimeError):
    """Base class for HTTP API domain errors."""


class AuthenticationError(APIError):
    """Missing or invalid API token.

    A plain exception, not a frozen dataclass: Starlette clears
    ``__traceback__`` while unwrapping handlers, which a frozen or slotted
    instance cannot accept.
    """

    def __init__(self, detail: str = "invalid or missing API token") -> None:
        super().__init__(detail)
        self.detail = detail


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
