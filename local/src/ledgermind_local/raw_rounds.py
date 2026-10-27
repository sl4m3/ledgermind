"""RawRound capture application service for the local API."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ledgermind_protocol import (
    RawRoundRequest,
    calculate_payload_digest,
    calculate_source_round_key,
)

from .persistence import SQLiteUnitOfWork


class RawRoundError(RuntimeError):
    """Base raw-round application error."""


class RawRoundConflict(RawRoundError):
    """Same source-round identity was submitted with a different body."""


class RawRoundDigestMismatch(RawRoundError):
    """Declared payload digest does not match canonical source+round body."""


class RawRoundTooLarge(RawRoundError):
    """The immutable raw payload exceeds the configured storage limit."""


@dataclass(frozen=True, slots=True)
class RawRoundIngestResult:
    raw_round_id: str
    duplicate: bool
    status: str
    core_command_id: str | None = None
    core_raw_round_id: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _source_round_key(request: RawRoundRequest) -> str:
    return calculate_source_round_key(
        {
            "source_system": request.source.system,
            "source_instance_id": request.source.instance_id,
            "source_profile_id": request.source.profile_id,
            "source_session_id": request.source.session_id,
            "source_round_id": request.source.round_id,
        }
    )


def _payload_json(request: RawRoundRequest) -> str:
    return json.dumps(
        request.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class RawRoundIngestHandler:
    def __init__(
        self,
        *,
        database_path: str | Path,
        max_raw_round_bytes: int = 5_000_000,
        retention_days: int = 30,
    ) -> None:
        self.database_path = database_path
        self.max_raw_round_bytes = max(int(max_raw_round_bytes), 1)
        self.retention_days = max(int(retention_days), 1)

    def handle(self, request: RawRoundRequest) -> RawRoundIngestResult:
        if calculate_payload_digest(request) != request.payload_digest:
            raise RawRoundDigestMismatch("payload_digest does not match source + round")
        event_ids = [event.event_id for event in request.round.events]
        if event_ids != request.source.event_ids:
            raise RawRoundError("source.event_ids must match round event order")
        if request.source.first_event_id not in (None, event_ids[0]):
            raise RawRoundError("source.first_event_id does not match round")
        if request.source.final_event_id not in (None, event_ids[-1]):
            raise RawRoundError("source.final_event_id does not match round")
        if len(event_ids) > 0 and request.round.completed_at < request.round.started_at:
            raise RawRoundError("round.completed_at must not precede started_at")

        payload_json = _payload_json(request)
        if len(payload_json.encode("utf-8")) > self.max_raw_round_bytes:
            raise RawRoundTooLarge("raw round payload exceeds configured limit")

        source_round_key = _source_round_key(request)
        with SQLiteUnitOfWork(self.database_path, write_transaction=True) as uow:
            existing = uow.raw_rounds.get_by_capture_identity(
                request.memory_space_id,
                source_round_key,
                request.source.source_schema_version,
            )
            if existing is not None:
                if existing.payload_digest != request.payload_digest:
                    raise RawRoundConflict(
                        "same source round identity already contains a different payload"
                    )
                return self._queue_core_delivery(
                    uow,
                    raw_round_id=existing.raw_round_id,
                    memory_space_id=request.memory_space_id,
                    request=request,
                    duplicate=True,
                )

            self._ensure_memory_space(uow.connection, request.memory_space_id)
            raw_round = uow.raw_rounds.insert(
                raw_round_id=str(uuid.uuid4()),
                memory_space_id=request.memory_space_id,
                source_system=request.source.system,
                source_instance_id=request.source.instance_id,
                source_profile_id=request.source.profile_id,
                source_session_id=request.source.session_id,
                source_round_id=request.source.round_id,
                source_round_key=source_round_key,
                capture_schema_version=request.source.source_schema_version,
                adapter_version=request.source.adapter_version,
                payload_json=payload_json,
                payload_digest=request.payload_digest,
                started_at=request.round.started_at.isoformat(),
                completed_at=request.round.completed_at.isoformat(),
                retention_expires_at=(
                    datetime.now(timezone.utc) + timedelta(days=self.retention_days)
                ).isoformat(timespec="seconds"),
            )
            return self._queue_core_delivery(
                uow,
                raw_round_id=raw_round.raw_round_id,
                memory_space_id=request.memory_space_id,
                request=request,
                duplicate=False,
            )

    @staticmethod
    def _queue_core_delivery(
        uow: SQLiteUnitOfWork,
        *,
        raw_round_id: str,
        memory_space_id: str,
        request: RawRoundRequest,
        duplicate: bool,
    ) -> RawRoundIngestResult:
        idempotency_key = request.payload_digest
        command_payload = json.dumps(
            {"raw_round_id": raw_round_id},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload_digest = "sha256:" + hashlib.sha256(
            command_payload.encode("utf-8")
        ).hexdigest()
        command = uow.raw_rounds.create_core_command(
            command_id=str(uuid.uuid4()),
            command_type="ingest_raw_round",
            memory_space_id=memory_space_id,
            idempotency_key=idempotency_key,
            payload_json=command_payload,
            payload_digest=payload_digest,
        )
        delivery = uow.raw_rounds.create_core_raw_round_delivery(
            raw_round_id=raw_round_id,
            memory_space_id=memory_space_id,
            command_id=command.command_id,
            idempotency_key=idempotency_key,
        )
        uow.commit()
        return RawRoundIngestResult(
            raw_round_id=raw_round_id,
            duplicate=duplicate,
            status="queued_for_core" if delivery.transport_status == "queued" else delivery.transport_status,
            core_command_id=command.command_id,
            core_raw_round_id=delivery.core_raw_round_id,
        )

    @staticmethod
    def _ensure_memory_space(
        connection: sqlite3.Connection, memory_space_id: str
    ) -> None:
        now = _now()
        connection.execute(
            """
            INSERT OR IGNORE INTO memory_spaces (
                memory_space_id, display_name, source_client, created_at, updated_at
            ) VALUES (?, NULL, 'ledgermind-integrations', ?, ?)
            """,
            (memory_space_id, now, now),
        )
