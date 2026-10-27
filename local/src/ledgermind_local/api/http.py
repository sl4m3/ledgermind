"""Shared helpers for HTTP API endpoints."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from starlette import status
from starlette.datastructures import Headers

_JSON_CONTENT_TYPE = "application/json"


def error_payload(code: str, detail: str) -> dict[str, str]:
    """Return stable error payload."""

    return {"code": code, "detail": detail}


def build_request_id(headers: Headers) -> str:
    """Read existing X-Request-ID header or generate a new UUID."""

    return headers.get("X-Request-ID", str(uuid.uuid4()))


def enforce_json_content_type(headers: Headers) -> None:
    """Reject non-JSON request payloads."""

    content_type = headers.get("content-type", "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type != _JSON_CONTENT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=error_payload(
                "unsupported_media_type", "content type must be application/json"
            ),
        )


def enforce_body_limit(headers: Headers, *, raw: bytes, max_bytes: int) -> None:
    """Enforce request body size limit using headers and actual payload size."""

    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    length = headers.get("content-length")
    if length is not None:
        try:
            if int(length) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=error_payload(
                        "request_too_large",
                        f"request body exceeds {max_bytes} bytes",
                    ),
                )
        except ValueError:
            pass

    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=error_payload(
                "request_too_large",
                f"request body exceeds {max_bytes} bytes",
            ),
        )


def validate_json_request(headers: Headers, *, raw: bytes, max_bytes: int) -> None:
    """Validate request shape expectations for JSON endpoints."""

    enforce_json_content_type(headers=headers)
    enforce_body_limit(headers=headers, raw=raw, max_bytes=max_bytes)


def validate_json_request_headers(headers: Headers, *, max_bytes: int) -> None:
    """Validate JSON media type and declared size before FastAPI parses a body."""

    enforce_json_content_type(headers=headers)
    enforce_body_limit(headers=headers, raw=b"", max_bytes=max_bytes)
