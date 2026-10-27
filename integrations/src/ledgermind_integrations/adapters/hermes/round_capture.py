"""Structural Hermes event -> RawRound conversion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ledgermind_protocol import (
    LedgerMindResolution,
    build_resolution_extension,
    validate_raw_round,
    validate_raw_round_extensions,
    with_payload_digest,
)


def _is_canonical_content_part(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    if not set(value).issubset({"type", "text", "data", "uri"}):
        return False
    part_type = value.get("type")
    if part_type == "text":
        return isinstance(value.get("text"), str)
    if part_type == "json":
        return value.get("data") is not None
    if part_type == "reference":
        return isinstance(value.get("uri"), str)
    return False


def _content(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        return [{"type": "text", "text": value}]
    if isinstance(value, list) and all(
        _is_canonical_content_part(item) for item in value
    ):
        return [dict(item) for item in value]
    return [{"type": "json", "data": value}]


def normalize_event(event: Mapping[str, Any], sequence: int, round_id: str) -> dict[str, Any]:
    event_id = str(event.get("event_id") or event.get("id") or f"{round_id}:{sequence}")
    kind = str(event.get("kind") or "message")
    if kind not in {"message", "tool_call", "tool_result"}:
        kind = "message"
    result: dict[str, Any] = {
        "event_id": event_id,
        "sequence": sequence,
        "kind": kind,
        "content": _content(event.get("content", event.get("api_content"))),
        "final": bool(event.get("final", False)),
    }
    for key in ("role", "tool_call_id", "tool_name", "arguments", "status"):
        if key in event and event[key] is not None:
            result[key] = event[key]
    if kind == "tool_call" and "arguments" not in result:
        result["arguments"] = {}
    if kind == "tool_result" and "status" not in result:
        result["status"] = "unknown"
    return result


def build_raw_round(
    *,
    memory_space_id: str,
    source_system: str,
    source_instance_id: str,
    profile_id: str,
    session_id: str,
    round_id: str,
    started_at: str,
    completed_at: str,
    events: Sequence[Mapping[str, Any]],
    adapter_version: str = "hermes-python/0.1.0",
    source_schema_version: int = 1,
    extensions: Mapping[str, Any] | None = None,
    source_extensions: Mapping[str, Any] | None = None,
    resolution: Mapping[str, Any] | LedgerMindResolution | None = None,
    resolution_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = [normalize_event(event, index, round_id) for index, event in enumerate(events)]
    event_ids = [event["event_id"] for event in normalized]
    top_level_extensions = dict(extensions) if extensions is not None else None
    canonical_source_extensions = dict(source_extensions or {})
    if resolution is not None and resolution_context is not None:
        raise ValueError("resolution and resolution_context were supplied together")
    if resolution is None:
        resolution = resolution_context
    if top_level_extensions is not None and "ledgermind_resolution" in top_level_extensions:
        if "ledgermind_resolution" in canonical_source_extensions or resolution is not None:
            raise ValueError("ledgermind_resolution was supplied more than once")
        canonical_source_extensions["ledgermind_resolution"] = top_level_extensions.pop(
            "ledgermind_resolution"
        )
    if resolution is not None:
        if "ledgermind_resolution" in canonical_source_extensions:
            raise ValueError("ledgermind_resolution was supplied more than once")
        resolution_values = (
            resolution.model_dump(mode="json")
            if isinstance(resolution, LedgerMindResolution)
            else dict(resolution)
        )
        resolution_payload = build_resolution_extension(
            session_id,
            metadata=resolution_values,
        )
        canonical_source_extensions["ledgermind_resolution"] = resolution_payload
    if source_system == "hermes" and "ledgermind_resolution" not in canonical_source_extensions:
        canonical_source_extensions["ledgermind_resolution"] = build_resolution_extension(session_id)

    source: dict[str, Any] = {
        "system": source_system,
        "instance_id": source_instance_id,
        "profile_id": profile_id,
        "session_id": session_id,
        "round_id": round_id,
        "first_event_id": event_ids[0],
        "final_event_id": event_ids[-1],
        "event_ids": event_ids,
        "source_schema_version": source_schema_version,
        "adapter_version": adapter_version,
    }
    if canonical_source_extensions:
        source["extensions"] = canonical_source_extensions
    payload = {
        "schema_version": 2,
        "idempotency_key": "sha256:" + "0" * 64,
        "memory_space_id": memory_space_id,
        "source": source,
        "round": {
            "started_at": started_at,
            "completed_at": completed_at,
            "events": normalized,
        },
    }
    if top_level_extensions:
        payload["extensions"] = top_level_extensions
    result = with_payload_digest(payload)
    result["idempotency_key"] = result["payload_digest"]
    if top_level_extensions is not None:
        validate_raw_round_extensions(result["extensions"])
    validate_raw_round(result)
    return result
