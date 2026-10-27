"""Validated entry points for public RawRound payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from .models import RawRoundRequest


class RawRoundValidationError(ValueError):
    """Payload is not a valid immutable RawRound request."""


def validate_raw_round(payload: Mapping[str, Any] | RawRoundRequest) -> RawRoundRequest:
    if isinstance(payload, RawRoundRequest):
        return payload
    if not isinstance(payload, Mapping):
        raise RawRoundValidationError("RawRound payload must be an object")
    try:
        return RawRoundRequest.model_validate(dict(payload))
    except ValidationError as exc:
        # Do not expose raw values in a transport exception; payloads can contain secrets.
        raise RawRoundValidationError("invalid RawRound payload") from exc


__all__ = ["RawRoundValidationError", "validate_raw_round"]
