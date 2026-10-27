"""Canonical JSON and digest helpers for RawRound."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast


def _normalize_rfc3339(value: object) -> object:
    if isinstance(value, list):
        return [_normalize_rfc3339(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_rfc3339(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_rfc3339(item) for key, item in value.items()}
    if not isinstance(value, str) or "T" not in value:
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return value
    normalized = parsed.isoformat().replace("+00:00", "Z")
    match = re.fullmatch(r"(?P<head>.*)\.(?P<fraction>\d+)(?P<zone>Z|[+-]\d{2}:\d{2})", normalized)
    if match is None:
        return normalized
    fraction = match.group("fraction").rstrip("0")
    return f"{match.group('head')}{('.' + fraction) if fraction else ''}{match.group('zone')}"


def _as_mapping(payload: object) -> dict[str, Any]:
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        value = model_dump(mode="json", exclude_none=True)
    elif isinstance(payload, Mapping):
        value = dict(payload)
    else:
        raise TypeError("RawRound payload must be an object")
    if not isinstance(value, dict):
        raise TypeError("RawRound payload must be an object")
    return value


def canonical_body(payload: object) -> dict[str, Any]:
    serialized = _as_mapping(payload)
    source = serialized.get("source")
    round_payload = serialized.get("round")
    if not isinstance(source, dict) or not isinstance(round_payload, dict):
        raise TypeError("RawRound payload must contain source and round objects")
    raw_events = round_payload.get("events")
    if not isinstance(raw_events, list):
        raise TypeError("RawRound payload must contain round.events")
    events: list[dict[str, Any]] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            raise TypeError("RawRound event must be an object")
        event = dict(raw_event)
        event.setdefault("content", [])
        event.setdefault("final", False)
        events.append(event)
    return {
        "source": source,
        "round": {**round_payload, "events": events},
    }


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        _normalize_rfc3339(canonical_body(payload)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def calculate_payload_digest(payload: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def calculate_raw_round_digest(payload: object) -> str:
    """Compatibility name inside the public protocol package."""

    return calculate_payload_digest(payload)


def calculate_source_round_key(source: object) -> str:
    """Derive the capture identity key from the five public source fields."""

    if isinstance(source, Mapping):
        raw_values: tuple[object, ...] = (
            source.get("system", source.get("source_system")),
            source.get("instance_id", source.get("source_instance_id")),
            source.get("profile_id", source.get("source_profile_id")),
            source.get("session_id", source.get("source_session_id")),
            source.get("round_id", source.get("source_round_id")),
        )
    else:
        raw_values = tuple(
            getattr(source, name, None)
            for name in ("system", "instance_id", "profile_id", "session_id", "round_id")
        )
        if any(value is None for value in raw_values):
            raw_values = tuple(
                getattr(source, name, None)
                for name in (
                    "source_system",
                    "source_instance_id",
                    "source_profile_id",
                    "source_session_id",
                    "source_round_id",
                )
            )
    if any(not isinstance(value, str) or not value for value in raw_values):
        raise ValueError("source round identity fields must be non-empty strings")
    values = tuple(value for value in raw_values if isinstance(value, str))
    return "sha256:" + hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def with_payload_digest(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = cast(dict[str, Any], json.loads(json.dumps(dict(payload), ensure_ascii=False)))
    digest = calculate_payload_digest(result)
    result["payload_digest"] = digest
    result["idempotency_key"] = digest
    return result


__all__ = [
    "calculate_payload_digest",
    "calculate_raw_round_digest",
    "calculate_source_round_key",
    "canonical_body",
    "canonical_json_bytes",
    "with_payload_digest",
]
