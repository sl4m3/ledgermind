from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from ledgermind_local.api.http import enforce_body_limit


def test_body_limit_rejects_declared_content_length() -> None:
    with pytest.raises(HTTPException) as error:
        enforce_body_limit(
            Headers({"content-length": "11"}),
            raw=b"short",
            max_bytes=10,
        )

    assert error.value.status_code == 413
    detail = error.value.detail
    assert isinstance(detail, dict)
    assert detail == {
        "code": "request_too_large",
        "detail": "request body exceeds 10 bytes",
    }


def test_body_limit_rejects_actual_body_without_declared_length() -> None:
    with pytest.raises(HTTPException) as error:
        enforce_body_limit(Headers({}), raw=b"01234567890", max_bytes=10)

    assert error.value.status_code == 413


def test_body_limit_rejects_non_positive_configuration() -> None:
    with pytest.raises(ValueError, match="max_bytes must be positive"):
        enforce_body_limit(Headers({}), raw=b"", max_bytes=0)
