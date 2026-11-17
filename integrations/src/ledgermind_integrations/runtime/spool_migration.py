"""One-time migration of persisted spool records to stable protocol names."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ledgermind_protocol import (
    LedgerMindContext,
    calculate_payload_digest,
    calculate_source_round_key,
)

from .spool import FileSpool

_OLD_SCHEMA_KEY = "api_version"
_OLD_CONTEXT_KEY = "ledgermind_context_v1"
_CONTEXT_KEY = "ledgermind_context"
_CONTEXT_SCHEMA_VERSION = 1
_RAW_ROUND_SCHEMA_VERSION = 2
_DELIVERY_KEYS = ("delivery", "request", "raw_round", "payload", "extensions")


class SpoolMigrationError(RuntimeError):
    """A persisted spool record cannot be migrated without losing meaning."""


@dataclass(frozen=True, slots=True)
class SpoolMigrationResult:
    recovered_inflight: int = 0
    migrated_pending: int = 0
    migrated_ready: int = 0
    migrated_failed: int = 0
    promoted_failed: int = 0
    retired_failed: int = 0


def _copy_json(value: Mapping[str, Any]) -> dict[str, Any]:
    copied = json.loads(json.dumps(dict(value), ensure_ascii=False))
    if not isinstance(copied, dict):
        raise SpoolMigrationError("spool record must be a JSON object")
    return copied


def _read_record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpoolMigrationError(f"cannot read spool record: {path.name}") from exc
    if not isinstance(value, dict):
        raise SpoolMigrationError(f"spool record is not an object: {path.name}")
    return value


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            temporary.chmod(0o600)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        path.chmod(0o600)
    except OSError as exc:
        raise SpoolMigrationError(f"cannot atomically rewrite spool record: {path.name}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _migrate_schema_field(record: dict[str, Any]) -> None:
    if _OLD_SCHEMA_KEY not in record:
        return
    old_value = record.pop(_OLD_SCHEMA_KEY)
    if old_value != _RAW_ROUND_SCHEMA_VERSION and old_value != str(_RAW_ROUND_SCHEMA_VERSION):
        raise SpoolMigrationError("unsupported historical RawRound schema")
    current_value = record.get("schema_version")
    if current_value is not None and current_value != _RAW_ROUND_SCHEMA_VERSION:
        raise SpoolMigrationError("spool record contains conflicting schema versions")
    record["schema_version"] = _RAW_ROUND_SCHEMA_VERSION


def _migrate_extensions(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SpoolMigrationError("spool extensions must be an object")
    extensions = dict(value)
    old_present = _OLD_CONTEXT_KEY in extensions
    current_present = _CONTEXT_KEY in extensions
    if old_present and current_present:
        raise SpoolMigrationError("spool record contains both context extension names")
    context_key = _OLD_CONTEXT_KEY if old_present else _CONTEXT_KEY
    if context_key not in extensions:
        return extensions
    raw_context = extensions[context_key]
    if not isinstance(raw_context, Mapping):
        raise SpoolMigrationError("context extension must be an object")
    context = dict(raw_context)
    context_schema = context.get("schema_version", _CONTEXT_SCHEMA_VERSION)
    if context_schema != _CONTEXT_SCHEMA_VERSION and context_schema != str(_CONTEXT_SCHEMA_VERSION):
        raise SpoolMigrationError("unsupported context extension schema")
    stable_context = {
        "schema_version": _CONTEXT_SCHEMA_VERSION,
        "retrieval_request_id": context.get("retrieval_request_id"),
        "delivered_value_ids": context.get("delivered_value_ids"),
    }
    try:
        validated = LedgerMindContext.model_validate(stable_context)
    except (TypeError, ValueError) as exc:
        raise SpoolMigrationError("invalid context provenance in spool record") from exc
    extensions.pop(_OLD_CONTEXT_KEY, None)
    extensions[_CONTEXT_KEY] = validated.model_dump(mode="json")
    return extensions


def _source_identity(payload: Mapping[str, Any]) -> str | None:
    source = payload.get("source")
    if not isinstance(source, Mapping):
        return None
    try:
        return calculate_source_round_key(source)
    except (TypeError, ValueError):
        return None


def _is_raw_round_payload(payload: Mapping[str, Any]) -> bool:
    return (
        "source" in payload
        and "round" in payload
        and (_OLD_SCHEMA_KEY in payload or "schema_version" in payload)
    )


def _migrate_raw_round(payload: Mapping[str, Any]) -> dict[str, Any]:
    before_identity = _source_identity(payload)
    result = _copy_json(payload)
    _migrate_schema_field(result)
    if "extensions" in result:
        result["extensions"] = _migrate_extensions(result["extensions"])

    source = result.get("source")
    round_payload = result.get("round")
    if isinstance(source, Mapping) and isinstance(round_payload, Mapping):
        events = round_payload.get("events")
        if isinstance(events, list):
            digest = calculate_payload_digest(result)
            result["payload_digest"] = digest
            result["idempotency_key"] = digest

    after_identity = _source_identity(result)
    if before_identity is not None and after_identity != before_identity:
        raise SpoolMigrationError("spool migration changed source round identity")
    return result


def _migrate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    result = _copy_json(record)
    _migrate_schema_field(result)

    for key in _DELIVERY_KEYS[1:4]:
        nested = result.get(key)
        if not isinstance(nested, Mapping):
            continue
        if _is_raw_round_payload(nested):
            result[key] = _migrate_raw_round(nested)
        elif "extensions" in nested:
            nested_result = _copy_json(nested)
            nested_result["extensions"] = _migrate_extensions(nested_result["extensions"])
            result[key] = nested_result

    if "extensions" in result:
        result["extensions"] = _migrate_extensions(result["extensions"])
    if _is_raw_round_payload(result):
        return _migrate_raw_round(result)
    return result


def migrate_spool_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return one migrated spool record without writing it to disk."""

    return _migrate_record(payload)


def _is_retryable_failed_record(record: Mapping[str, Any]) -> bool:
    request = record.get("request")
    delivery = record.get("delivery")
    if not isinstance(request, Mapping) or not isinstance(delivery, Mapping):
        return False
    return delivery.get("retryable") is True or record.get("retryable") is True


def _recover_inflight(spool: FileSpool) -> int:
    # TTL-aware recovery: only records whose claim is older than the spool's
    # inflight TTL are returned to ready/. A fresh in-flight record is owned by a
    # live worker/drain; stealing it here would duplicate delivery work. This
    # mirrors FileSpool._reclaim_expired_inflight so a single drain under a
    # shared lock never re-queues another instance's live claim.
    #
    # A missing claimed_at is a live claim, not an old one: pop_ready renames
    # ready/->inflight/ before it rewrites the record with claimed_at, and
    # rename() preserves mtime, so mtime is not evidence of age. Residual risk
    # (accepted): a process dying inside that window leaves the record in
    # inflight/ without claimed_at forever, recoverable only by hand. Losing or
    # duplicating a round is worse than one stuck record.
    recovered = 0
    now = time.time()
    ttl = spool.inflight_ttl_seconds
    for path in sorted(spool.inflight_dir.glob("*.json")):
        payload = _migrate_record(_read_record(path))
        delivery = payload.get("delivery")
        raw_claimed = delivery.get("claimed_at") if isinstance(delivery, dict) else None
        if raw_claimed is None:
            continue
        try:
            claimed_at = float(raw_claimed)
        except (TypeError, ValueError):
            # An unreadable claim is treated as live, not as expired.
            continue
        if now - claimed_at < ttl:
            continue
        if not isinstance(delivery, dict):
            delivery = {}
            payload["delivery"] = delivery
        delivery.pop("worker_id", None)
        delivery.pop("claimed_at", None)
        delivery["next_attempt_at"] = 0.0
        _atomic_write(spool.ready_dir / path.name, payload)
        path.unlink(missing_ok=True)
        recovered += 1
    return recovered


def _migrate_directory(directory: Path) -> int:
    migrated = 0
    for path in sorted(directory.glob("*.json")):
        original = _read_record(path)
        current = _migrate_record(original)
        if current == original:
            continue
        _atomic_write(path, current)
        migrated += 1
    return migrated


def _failed_promotion_exhausted(
    spool: FileSpool, delivery: Mapping[str, Any], path: Path, now: float
) -> str | None:
    """Name the limit that forbids promoting a quarantined record back to ready/.

    Both limits live on the spool instance, so they come from integration config
    and never from literals here.
    """

    try:
        attempts = int(delivery.get("attempts", 0))
    except (TypeError, ValueError):
        attempts = 0
    if attempts >= spool.retryable_failed_max_attempts:
        return "attempts"
    raw_failed_at = delivery.get("failed_at")
    failed_at: float | None
    if raw_failed_at is None:
        # Legacy quarantines predate failed_at: their age is the file's age.
        try:
            failed_at = path.stat().st_mtime
        except OSError:
            failed_at = None
    else:
        try:
            failed_at = float(raw_failed_at)
        except (TypeError, ValueError):
            failed_at = None  # an unreadable age is not evidence of expiry
    if failed_at is not None and now - failed_at >= spool.retryable_failed_max_age_seconds:
        return "age"
    return None


def _migrate_failed(spool: FileSpool) -> tuple[int, int, int]:
    """Rewrite failed/ records and promote the ones still worth another attempt.

    Promotion is bounded by attempt count and by the age of the latest failure:
    a permanent 4xx (bad key, rejected payload) never turns into acceptance by
    retrying, so exhausted records stay in failed/ with ``retryable=False``,
    ``retired_at`` and ``retirement_reason`` instead of being resent forever.
    """

    migrated = 0
    promoted = 0
    retired = 0
    now = time.time()
    for path in sorted(spool.failed_dir.glob("*.json")):
        original = _read_record(path)
        current = _migrate_record(original)
        if current != original:
            _atomic_write(path, current)
            migrated += 1
        if not _is_retryable_failed_record(current):
            continue
        delivery = current.get("delivery")
        if not isinstance(delivery, dict):
            continue
        exhausted = _failed_promotion_exhausted(spool, delivery, path, now)
        if exhausted is not None:
            # Keep the payload for manual recovery; only stop the automatic
            # promotion loop.
            delivery["retryable"] = False
            delivery["retired_at"] = now
            delivery["retirement_reason"] = f"retryable_failed_{exhausted}_exhausted"
            if "retryable" in current:
                current["retryable"] = False  # legacy top-level flag
            _atomic_write(path, current)
            retired += 1
            continue
        delivery.pop("failure_reason", None)
        delivery.pop("failed_at", None)
        delivery.pop("worker_id", None)
        delivery.pop("claimed_at", None)
        delivery["next_attempt_at"] = 0.0
        _atomic_write(spool.ready_dir / path.name, current)
        path.unlink(missing_ok=True)
        promoted += 1
    return migrated, promoted, retired


def migrate_spool(spool: FileSpool | str | Path) -> SpoolMigrationResult:
    """Recover and rewrite all persisted records before delivery starts.

    Failed records are promoted back to ready/ only while they stay within the
    spool's attempt and age limits; exhausted ones remain in failed/ with
    ``retryable=False`` and a retirement reason.
    """

    target = spool if isinstance(spool, FileSpool) else FileSpool(spool)
    target._ensure()
    recovered = _recover_inflight(target)
    pending = _migrate_directory(target.pending_dir)
    ready = _migrate_directory(target.ready_dir)
    failed, promoted, retired = _migrate_failed(target)
    return SpoolMigrationResult(
        recovered_inflight=recovered,
        migrated_pending=pending,
        migrated_ready=ready,
        migrated_failed=failed,
        promoted_failed=promoted,
        retired_failed=retired,
    )


__all__ = [
    "SpoolMigrationError",
    "SpoolMigrationResult",
    "migrate_spool",
    "migrate_spool_payload",
]
