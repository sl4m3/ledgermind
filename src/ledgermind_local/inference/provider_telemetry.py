"""Secret-free provider telemetry emitted by the Local runtime.

The file is intentionally append-only and opt-in.  It records task and real
HTTP-attempt boundaries, never prompts, response bodies, headers or URLs.
Provider-reported token counts are retained as bounded numeric accounting
metadata; missing usage is explicitly marked unknown.  The lifecycle harness enables it with
``LEDGERMIND_PROVIDER_TELEMETRY_PATH`` and owns the resulting evidence file.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TELEMETRY_ENV = "LEDGERMIND_PROVIDER_TELEMETRY_PATH"
_LOCK = threading.Lock()
_CURRENT_OPERATION: ContextVar[str | None] = ContextVar(
    "ledgermind_provider_operation", default=None
)
_CURRENT_CONTEXT: ContextVar[dict[str, object]] = ContextVar(
    "ledgermind_provider_context", default={}
)


@contextmanager
def operation_context(operation: object, **metadata: object) -> Iterator[None]:
    """Attach safe task/attempt metadata to one provider request scope.

    The context never contains prompts or response bodies.  It exists so a
    retry/fallback transport can keep the same task correlation even though
    the actual HTTP call is made several stack frames below Core.
    """

    normalized_operation = operation_label(operation) if operation else None
    token = _CURRENT_OPERATION.set(normalized_operation)
    context = {str(key): value for key, value in metadata.items() if value is not None}
    context_token = _CURRENT_CONTEXT.set(context)
    try:
        yield
    finally:
        _CURRENT_CONTEXT.reset(context_token)
        _CURRENT_OPERATION.reset(token)


def current_operation() -> str | None:
    return _CURRENT_OPERATION.get()


def current_operation_context() -> dict[str, object]:
    """Return a copy of the current content-free request correlation context."""

    return dict(_CURRENT_CONTEXT.get())


def _text(value: object, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _path() -> Path | None:
    value = os.environ.get(TELEMETRY_ENV, "")
    if not value.strip():
        return None
    return Path(value).expanduser()


def _append(
    payload: Mapping[str, object], *, keep_null_keys: set[str] | None = None
) -> None:
    target = _path()
    if target is None:
        return
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    keep_null = keep_null_keys or set()
    safe = {
        key: value
        for key, value in payload.items()
        if value is not None or key in keep_null
    }
    safe.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
    encoded = json.dumps(
        safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    with _LOCK:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
        os.chmod(target, 0o600)


def operation_label(operation: object, *, default: str = "unknown") -> str:
    """Map Core's opaque operation names to stable observability labels."""

    normalized = _text(operation, default)
    return {
        "extract_claims": "operational_claim_extraction",
        "extract_values": "operational_claim_extraction",
        "resolve_subjects": "subject_resolution",
        "consolidate_values": "background_consolidation",
        "semantic_repair": "semantic_repair",
        "subject_query": "subject_candidates",
        "object_query": "object_cards",
        "object_mention": "object_cards",
        "object_card": "object_cards",
        "value_record": "knowledge_values",
        "knowledge": "knowledge_values",
        "facet_catalog": "facets",
        "retrieval_query": "retrieval_query",
    }.get(normalized, normalized)


def record_task(
    *,
    kind: str,
    operation: object,
    provider_profile_fingerprint: object = None,
    model: object = None,
    task_count: int = 1,
    item_count: int | None = None,
    cache_hits: int | None = None,
    cache_misses: int | None = None,
    task_id: object = None,
    root_task_id: object = None,
    attempt_index: int | None = None,
    request_reason: object = None,
    structured_output_mode: object = None,
    fallback_from: object = None,
    fallback_to: object = None,
) -> None:
    """Record a provider task without recording its content."""

    payload: dict[str, Any] = {
        "event": "task",
        "kind": _text(kind, "unknown"),
        "operation": operation_label(operation),
        "provider_profile_fingerprint": _text(provider_profile_fingerprint) or None,
        "model": _text(model) or None,
        "task_count": _non_negative_int(task_count) or 0,
        "item_count": _non_negative_int(item_count),
        "cache_hits": _non_negative_int(cache_hits),
        "cache_misses": _non_negative_int(cache_misses),
        "task_id": _text(task_id) or None,
        "root_task_id": _text(root_task_id) or None,
        "attempt_index": _non_negative_int(attempt_index),
        "request_reason": _text(request_reason) or None,
        "structured_output_mode": _text(structured_output_mode) or None,
        "fallback_from": _text(fallback_from) or None,
        "fallback_to": _text(fallback_to) or None,
    }
    _append(payload)


def record_counter(name: str, value: int = 1, **fields: object) -> None:
    """Record one bounded counter increment."""

    increment = _non_negative_int(value)
    if increment is None:
        return
    payload: dict[str, Any] = {
        "event": "counter",
        "counter": _text(name, "unknown"),
        "value": increment,
    }
    for key in ("operation", "provider_profile_fingerprint", "model"):
        if key in fields:
            payload[key] = _text(fields[key]) or None
    _append(payload)


def record_http_attempt(
    *,
    kind: str,
    operation: object,
    provider_profile_fingerprint: object = None,
    transport: str,
    model: object,
    duration_ms: float,
    status: str,
    request_id: object = None,
    http_status: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    batch_item_count: int = 1,
    retry_index: int = 0,
    total_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    reported_cost: float | int | None = None,
    usage_unknown: bool | None = None,
    operation_item_counts: Mapping[str, int] | None = None,
    metadata: Mapping[str, object] | None = None,
    task_id: object = None,
    root_task_id: object = None,
    attempt_index: int | None = None,
    request_reason: object = None,
    structured_output_mode: object = None,
    fallback_from: object = None,
    fallback_to: object = None,
    configured_routes: object = None,
    served_by: object = None,
    wire_reasoning_effort: object = None,
    wire_thinking: object = None,
) -> None:
    """Record one actual HTTP attempt using only safe scalar metadata."""

    context = current_operation_context()
    if metadata is not None:
        context.update({str(key): value for key, value in metadata.items()})

    def context_text(name: str, explicit: object) -> str:
        return _text(explicit) or _text(context.get(name))

    def context_int(name: str, explicit: int | None) -> int | None:
        return (
            _non_negative_int(explicit)
            if explicit is not None
            else _non_negative_int(context.get(name))
        )

    input_count = _non_negative_int(input_tokens)
    output_count = _non_negative_int(output_tokens)
    total_count = _non_negative_int(total_tokens)
    if total_count is None and input_count is not None and output_count is not None:
        total_count = input_count + output_count
    if usage_unknown is None:
        usage_unknown = (
            input_count is None and output_count is None and total_count is None
        )
    safe_item_counts: dict[str, int] | None = None
    if isinstance(operation_item_counts, Mapping):
        safe_item_counts = {
            str(key): int(value)
            for key, value in operation_item_counts.items()
            if isinstance(key, str)
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        }
    request_id_text = _text(request_id) or f"local-{uuid.uuid4().hex}"
    operation_name = operation_label(operation or context.get("operation"))
    reason = context_text("request_reason", request_reason)
    if retry_index > 0:
        reason = "transport_retry"
    elif not reason:
        reason = (
            "provider_probe"
            if operation_name in {"capability_probe", "provider_probe"}
            else "primary"
        )
    payload: dict[str, Any] = {
        "event": "http",
        "kind": _text(kind, "unknown"),
        "operation": operation_name,
        "request_id": request_id_text,
        "task_id": context_text("task_id", task_id) or "unknown",
        "root_task_id": context_text("root_task_id", root_task_id) or "unknown",
        "attempt_index": context_int("attempt_index", attempt_index) or 0,
        "request_reason": reason,
        "structured_output_mode": context_text(
            "structured_output_mode", structured_output_mode
        )
        or "unknown",
        "fallback_from": context_text("fallback_from", fallback_from) or None,
        "fallback_to": context_text("fallback_to", fallback_to) or None,
        "configured_routes": (
            [str(route) for route in configured_routes if isinstance(route, str)]
            if isinstance(configured_routes, (list, tuple))
            else None
        ),
        "served_by": _text(served_by) or None,
        "provider_profile_fingerprint": _text(provider_profile_fingerprint) or None,
        "transport": _text(transport, "unknown"),
        "model": _text(model, "unknown"),
        "duration_ms": round(max(float(duration_ms), 0.0), 3),
        "status": _text(status, "unknown"),
        "http_status": http_status if isinstance(http_status, int) else None,
        "input_tokens": input_count,
        "output_tokens": output_count,
        "total_tokens": total_count,
        "cached_input_tokens": _non_negative_int(cached_input_tokens),
        "usage_unknown": bool(usage_unknown),
        "reported_cost": (
            float(reported_cost)
            if isinstance(reported_cost, (int, float))
            and not isinstance(reported_cost, bool)
            and reported_cost >= 0
            else None
        ),
        "batch_item_count": _non_negative_int(batch_item_count) or 0,
        "retry_index": _non_negative_int(retry_index) or 0,
        "wire_reasoning_effort": _text(wire_reasoning_effort) or None,
        "wire_thinking": _text(wire_thinking) or None,
        "operation_item_counts": safe_item_counts,
    }
    _append(
        payload,
        keep_null_keys={
            "http_status",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "reported_cost",
            "wire_reasoning_effort",
            "wire_thinking",
            "operation_item_counts",
            "fallback_from",
            "fallback_to",
            "configured_routes",
            "served_by",
        },
    )


__all__ = [
    "TELEMETRY_ENV",
    "current_operation",
    "current_operation_context",
    "operation_context",
    "operation_label",
    "record_counter",
    "record_http_attempt",
    "record_task",
]
