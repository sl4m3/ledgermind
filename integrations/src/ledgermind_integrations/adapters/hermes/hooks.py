"""Hermes capture hooks and delayed final-event promotion."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ledgermind_protocol import LedgerMindResolution, build_resolution_extension

from ...runtime.spool import FileSpool
from .config import HermesConfig
from .round_capture import build_raw_round

_RAW_ROUND_SNAPSHOT_ENV = "LEDGERMIND_HERMES_RAW_ROUND_SNAPSHOT_PATH"


def _write_raw_round_snapshot(payload: Mapping[str, Any]) -> None:
    """Persist a private pre-delivery copy for an external host verifier.

    Local intentionally removes raw request bodies after accepting them.  The
    official-host lifecycle gate therefore needs a copy made before the
    delivery worker can clear that body.  The file is opt-in, private, and is
    never sent as part of the hook trace.
    """

    configured = os.environ.get(_RAW_ROUND_SNAPSHOT_ENV)
    if not configured:
        return
    target = Path(configured).expanduser()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    encoded = (
        json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    try:
        with temporary.open("wb") as handle:
            os.chmod(temporary, 0o600)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


class HermesRoundCapture:
    def __init__(self, config: HermesConfig, spool: FileSpool | None = None) -> None:
        self.config = config
        self.spool = spool or FileSpool(
            config.spool_dir,
            max_payload_bytes=config.max_raw_round_bytes,
            max_bytes=config.max_spool_bytes,
            max_files=config.max_spool_files,
            inflight_ttl_seconds=config.inflight_ttl_seconds,
        )

    def capture_or_defer(
        self,
        *,
        session_id: str,
        round_id: str,
        started_at: str,
        completed_at: str,
        events: Sequence[Mapping[str, Any]],
        pending_metadata: Mapping[str, Any] | None = None,
        extensions: Mapping[str, Any] | None = None,
        source_extensions: Mapping[str, Any] | None = None,
        resolution: Mapping[str, Any] | LedgerMindResolution | None = None,
    ) -> Path:
        pending = dict(pending_metadata or {})
        effective_extensions = extensions
        if effective_extensions is None:
            candidate = pending.get("extensions")
            if isinstance(candidate, Mapping):
                effective_extensions = candidate
        if effective_extensions is not None:
            pending["extensions"] = dict(effective_extensions)
        effective_source_extensions = source_extensions
        if effective_source_extensions is None:
            candidate = pending.get("source_extensions")
            if isinstance(candidate, Mapping):
                effective_source_extensions = candidate
        if effective_source_extensions is None:
            effective_source_extensions = {
                "ledgermind_resolution": self.resolution_extension(
                    session_id,
                    metadata=pending_metadata,
                    resolution=resolution,
                )
            }
        else:
            effective_source_extensions = dict(effective_source_extensions)
            if "ledgermind_resolution" not in effective_source_extensions:
                effective_source_extensions["ledgermind_resolution"] = (
                    self.resolution_extension(
                        session_id,
                        metadata=pending_metadata,
                        resolution=resolution,
                    )
                )
            if resolution is not None:
                effective_source_extensions["ledgermind_resolution"] = (
                    resolution.model_dump(mode="json")
                    if isinstance(resolution, LedgerMindResolution)
                    else LedgerMindResolution.model_validate(resolution).model_dump(mode="json")
                )
        pending["source_extensions"] = dict(effective_source_extensions)
        if not events or not any(bool(event.get("final")) for event in events):
            pending.setdefault("session_id", session_id)
            pending.setdefault("round_id", round_id)
            pending.setdefault("external_turn_id", None)
            pending.setdefault("started_at", started_at)
            pending.setdefault("completed_at", completed_at)
            pending.setdefault("first_message_id", None)
            pending.setdefault("last_message_id", None)
            pending.setdefault("user_message_id", None)
            pending.setdefault("assistant_message_id", None)
            pending.setdefault(
                "known_event_ids",
                [
                    str(event.get("event_id"))
                    for event in events
                    if event.get("event_id") is not None
                ],
            )
            pending.setdefault(
                "known_tool_events",
                [
                    str(event.get("event_id"))
                    for event in events
                    if event.get("kind") in {"tool_call", "tool_result"}
                    and event.get("event_id") is not None
                ],
            )
            pending["events"] = [dict(event) for event in events]
            return self.spool.enqueue_pending(round_id, pending)
        payload = build_raw_round(
            memory_space_id=self.config.memory_space_id,
            source_system="hermes",
            source_instance_id=self.config.source_instance_id,
            profile_id=self.config.profile_id,
            session_id=session_id,
            round_id=round_id,
            started_at=started_at,
            completed_at=completed_at,
            events=events,
            extensions=effective_extensions,
            source_extensions=effective_source_extensions,
            adapter_version=self.config.adapter_version,
            source_schema_version=self.config.source_schema_version,
        )
        _write_raw_round_snapshot(payload)
        return self.spool.enqueue_ready(payload["idempotency_key"], payload)

    def resolution_extension(
        self,
        session_id: str,
        *,
        metadata: Mapping[str, Any] | None = None,
        resolution: Mapping[str, Any] | LedgerMindResolution | None = None,
    ) -> dict[str, object]:
        if isinstance(resolution, LedgerMindResolution):
            values = resolution.model_dump(mode="json")
            values["conversation_id"] = session_id
            return LedgerMindResolution.model_validate(values).model_dump(mode="json")
        merged: dict[str, Any] = dict(metadata or {})
        if resolution is not None:
            merged.update(dict(resolution))
        return build_resolution_extension(
            session_id,
            metadata=merged,
            project_id=self.config.project_id,
            repository_id=self.config.repository_id,
            task_id=self.config.task_id,
            working_directory=self.config.working_directory,
            repository_root=self.config.repository_root,
            repository_mapping=self.config.repository_mapping,
        )


class PendingCaptureWorker:
    """Promote pending captures after state.db exposes a final event."""

    _BACKOFF_SECONDS = (1.0, 3.0, 10.0, 30.0, 120.0)

    def __init__(self, capture: HermesRoundCapture, *, max_attempts: int = 3) -> None:
        self.capture = capture
        self.max_attempts = max(int(max_attempts), 1)

    def run_once(
        self, resolver: Callable[[Mapping[str, Any]], Sequence[Mapping[str, Any]] | None]
    ) -> int:
        promoted = 0
        for item_name, pending in self.capture.spool.pop_pending():
            delivery = pending.get("delivery")
            if not isinstance(delivery, dict):
                delivery = {"attempts": 0, "next_attempt_at": 0.0}
                pending["delivery"] = delivery
            attempts = self._attempt_number(delivery) + 1
            delivery["attempts"] = attempts
            resolver_reason = "source_range_not_found"
            try:
                events = resolver(pending)
            except Exception as exc:  # noqa: BLE001
                events = None
                resolver_reason = self._resolver_failure_reason(exc)
            if not events or not any(bool(event.get("final")) for event in events):
                self._retry_pending(
                    item_name,
                    pending,
                    attempts=attempts,
                    reason=(
                        resolver_reason
                        if events is None
                        else "final_message_not_committed"
                    ),
                    until_deadline=True,
                )
                continue
            try:
                payload = build_raw_round(
                    memory_space_id=self.capture.config.memory_space_id,
                    source_system="hermes",
                    source_instance_id=self.capture.config.source_instance_id,
                    profile_id=self.capture.config.profile_id,
                    session_id=str(pending["session_id"]),
                    round_id=str(pending["round_id"]),
                    started_at=str(pending["started_at"]),
                    completed_at=str(pending["completed_at"]),
                    events=events,
                    extensions=(
                        pending.get("extensions")
                        if isinstance(pending.get("extensions"), Mapping)
                        else None
                    ),
                    source_extensions=(
                        pending.get("source_extensions")
                        if isinstance(pending.get("source_extensions"), Mapping)
                        else {
                            "ledgermind_resolution": self.capture.resolution_extension(
                                str(pending["session_id"]),
                                metadata=pending,
                            )
                        }
                    ),
                    adapter_version=self.capture.config.adapter_version,
                    source_schema_version=self.capture.config.source_schema_version,
                )
            except Exception as exc:  # noqa: BLE001
                reason = "digest_mismatch" if "digest" in str(exc).lower() else "invalid_source_data"
                self.capture.spool.fail_pending(item_name, reason)
                continue
            try:
                self.capture.spool.enqueue_ready(
                    payload["idempotency_key"],
                    payload,
                    exclude=(self.capture.spool.pending_dir / item_name,),
                )
            except Exception:  # noqa: BLE001
                self._retry_pending(
                    item_name,
                    pending,
                    attempts=attempts,
                    reason="ready_queue_unavailable",
                    until_deadline=False,
                )
                continue
            self.capture.spool.complete_pending(item_name)
            promoted += 1
        return promoted

    def _retry_pending(
        self,
        item_name: str,
        pending: dict[str, Any],
        *,
        attempts: int,
        reason: str,
        until_deadline: bool,
    ) -> None:
        delivery = pending.setdefault("delivery", {})
        if not isinstance(delivery, dict):
            delivery = {}
            pending["delivery"] = delivery
        deadline = self._deadline(delivery)
        if deadline is not None and time.time() >= deadline:
            self.capture.spool.fail_pending(item_name, reason)
            return
        if not until_deadline and attempts >= self.max_attempts:
            self.capture.spool.fail_pending(item_name, reason)
            return
        index = min(max(attempts - 1, 0), len(self._BACKOFF_SECONDS) - 1)
        delivery["last_error"] = reason
        delivery["next_attempt_at"] = time.time() + self._BACKOFF_SECONDS[index]
        self.capture.spool.retry_pending(item_name, pending)

    @staticmethod
    def _attempt_number(delivery: Mapping[str, Any]) -> int:
        try:
            return max(int(delivery.get("attempts", 0)), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _deadline(delivery: Mapping[str, Any]) -> float | None:
        value = delivery.get("deadline_at")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resolver_failure_reason(exc: Exception) -> str:
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            return "state_db_locked"
        return "source_range_not_found"
