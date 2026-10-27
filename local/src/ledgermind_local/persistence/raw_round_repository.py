"""SQLite repositories for transport rounds and Core delivery."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class RawRoundRecord:
    raw_round_id: str
    memory_space_id: str
    source_system: str
    source_instance_id: str
    source_profile_id: str
    source_session_id: str
    source_round_id: str
    source_round_key: str
    capture_schema_version: int
    adapter_version: str
    payload_json: str
    payload_digest: str
    started_at: str
    completed_at: str
    received_at: str
    retention_expires_at: str | None


@dataclass(frozen=True, slots=True)
class CoreCommandRecord:
    command_id: str
    command_type: str
    memory_space_id: str
    idempotency_key: str
    payload_json: str
    payload_digest: str
    status: str
    attempts: int
    available_at: str
    lease_expires_at: str | None
    claimed_by: str | None
    completed_at: str | None
    result_json: str | None
    last_error_code: str | None
    last_error_detail: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class CoreRawRoundDeliveryRecord:
    raw_round_id: str
    memory_space_id: str
    command_id: str
    idempotency_key: str
    transport_status: str
    core_raw_round_id: str | None
    last_error_code: str | None
    created_at: str
    updated_at: str


class SQLiteRawRoundRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_by_capture_identity(
        self,
        memory_space_id: str,
        source_round_key: str,
        capture_schema_version: int,
    ) -> RawRoundRecord | None:
        row = self._connection.execute(
            """
            SELECT raw_rounds.raw_round_id, raw_rounds.memory_space_id,
                   raw_rounds.source_system, raw_rounds.source_instance_id,
                   raw_rounds.source_profile_id, raw_rounds.source_session_id,
                   raw_rounds.source_round_id, raw_rounds.source_round_key,
                   raw_rounds.capture_schema_version, raw_rounds.adapter_version,
                   COALESCE(raw_round_payloads.payload_json, raw_rounds.payload_json) AS payload_json,
                   raw_rounds.payload_digest, raw_rounds.started_at, raw_rounds.completed_at,
                   raw_rounds.received_at,
                   COALESCE(raw_round_payloads.retention_expires_at,
                            raw_rounds.retention_expires_at) AS retention_expires_at
            FROM raw_rounds
            LEFT JOIN raw_round_payloads
                ON raw_round_payloads.raw_round_id = raw_rounds.raw_round_id
            WHERE raw_rounds.memory_space_id = ?
              AND raw_rounds.source_round_key = ?
              AND raw_rounds.capture_schema_version = ?
            """,
            (memory_space_id, source_round_key, capture_schema_version),
        ).fetchone()
        return self._round_from_row(row) if row is not None else None

    def get(self, raw_round_id: str) -> RawRoundRecord | None:
        row = self._connection.execute(
            """
            SELECT raw_rounds.raw_round_id, raw_rounds.memory_space_id,
                   raw_rounds.source_system, raw_rounds.source_instance_id,
                   raw_rounds.source_profile_id, raw_rounds.source_session_id,
                   raw_rounds.source_round_id, raw_rounds.source_round_key,
                   raw_rounds.capture_schema_version, raw_rounds.adapter_version,
                   COALESCE(raw_round_payloads.payload_json, raw_rounds.payload_json) AS payload_json,
                   raw_rounds.payload_digest, raw_rounds.started_at, raw_rounds.completed_at,
                   raw_rounds.received_at,
                   COALESCE(raw_round_payloads.retention_expires_at,
                            raw_rounds.retention_expires_at) AS retention_expires_at
            FROM raw_rounds
            LEFT JOIN raw_round_payloads
                ON raw_round_payloads.raw_round_id = raw_rounds.raw_round_id
            WHERE raw_rounds.raw_round_id = ?
            """,
            (raw_round_id,),
        ).fetchone()
        return self._round_from_row(row) if row is not None else None

    def insert(
        self,
        *,
        raw_round_id: str,
        memory_space_id: str,
        source_system: str,
        source_instance_id: str,
        source_profile_id: str,
        source_session_id: str,
        source_round_id: str,
        source_round_key: str,
        capture_schema_version: int,
        adapter_version: str,
        payload_json: str,
        payload_digest: str,
        started_at: str,
        completed_at: str,
        retention_expires_at: str | None = None,
    ) -> RawRoundRecord:
        received_at = _now()
        self._connection.execute(
            """
            INSERT INTO raw_rounds (
                raw_round_id, memory_space_id, source_system, source_instance_id,
                source_profile_id, source_session_id, source_round_id, source_round_key,
                capture_schema_version, adapter_version, payload_json, payload_digest,
                started_at, completed_at, received_at, retention_expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_round_id,
                memory_space_id,
                source_system,
                source_instance_id,
                source_profile_id,
                source_session_id,
                source_round_id,
                source_round_key,
                capture_schema_version,
                adapter_version,
                "{}",
                payload_digest,
                started_at,
                completed_at,
                received_at,
                retention_expires_at,
            ),
        )
        self._connection.execute(
            """
            INSERT INTO raw_round_payloads (
                raw_round_id, payload_json, payload_bytes, retention_expires_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                raw_round_id,
                payload_json,
                len(payload_json.encode("utf-8")),
                retention_expires_at,
            ),
        )
        result = self.get(raw_round_id)
        if result is None:
            raise RuntimeError("raw round insert did not produce a row")
        return result

    def create_core_command(
        self,
        *,
        command_id: str,
        command_type: str,
        memory_space_id: str,
        idempotency_key: str,
        payload_json: str,
        payload_digest: str,
        available_at: str | None = None,
    ) -> CoreCommandRecord:
        if not command_type.strip():
            raise ValueError("command_type must not be empty")
        if not payload_digest.startswith("sha256:"):
            raise ValueError("payload_digest must use sha256 prefix")
        existing = self._connection.execute(
            """
            SELECT * FROM core_commands
            WHERE memory_space_id = ? AND idempotency_key = ?
            """,
            (memory_space_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            if (
                str(existing["command_type"]) != command_type
                or str(existing["payload_json"]) != payload_json
                or str(existing["payload_digest"]) != payload_digest
            ):
                raise ValueError("core command payload conflict")
            return self._core_command_from_row(existing)

        created_at = _now()
        self._connection.execute(
            """
            INSERT INTO core_commands (
                command_id, command_type, memory_space_id, idempotency_key,
                payload_json, payload_digest, status, attempts, available_at,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
            """,
            (
                command_id,
                command_type,
                memory_space_id,
                idempotency_key,
                payload_json,
                payload_digest,
                available_at or created_at,
                created_at,
            ),
        )
        row = self._connection.execute(
            "SELECT * FROM core_commands WHERE command_id = ?", (command_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("core command insert did not produce a row")
        return self._core_command_from_row(row)

    def get_core_command_by_idempotency(
        self,
        memory_space_id: str,
        idempotency_key: str,
    ) -> CoreCommandRecord | None:
        row = self._connection.execute(
            """
            SELECT * FROM core_commands
            WHERE memory_space_id = ? AND idempotency_key = ?
            """,
            (memory_space_id, idempotency_key),
        ).fetchone()
        return self._core_command_from_row(row) if row is not None else None

    def create_core_raw_round_delivery(
        self,
        *,
        raw_round_id: str,
        memory_space_id: str,
        command_id: str,
        idempotency_key: str,
    ) -> CoreRawRoundDeliveryRecord:
        now = _now()
        self._connection.execute(
            """
            INSERT INTO raw_round_core_deliveries (
                raw_round_id, memory_space_id, command_id, idempotency_key,
                transport_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'queued', ?, ?)
            ON CONFLICT(raw_round_id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (raw_round_id, memory_space_id, command_id, idempotency_key, now, now),
        )
        result = self.get_core_raw_round_delivery(raw_round_id)
        if result is None:
            raise RuntimeError("raw round delivery insert did not produce a row")
        return result

    def get_core_raw_round_delivery(
        self, raw_round_id: str
    ) -> CoreRawRoundDeliveryRecord | None:
        row = self._connection.execute(
            "SELECT * FROM raw_round_core_deliveries WHERE raw_round_id = ?",
            (raw_round_id,),
        ).fetchone()
        return self._core_raw_round_delivery_from_row(row) if row is not None else None

    def update_core_raw_round_delivery(
        self,
        raw_round_id: str,
        *,
        transport_status: str,
        core_raw_round_id: str | None = None,
        error_code: str | None = None,
    ) -> bool:
        if transport_status not in {"queued", "accepted", "rejected", "retry_wait"}:
            raise ValueError(f"unsupported raw round delivery status: {transport_status}")
        updated = self._connection.execute(
            """
            UPDATE raw_round_core_deliveries
            SET transport_status = ?, core_raw_round_id = COALESCE(?, core_raw_round_id),
                last_error_code = ?, updated_at = ?
            WHERE raw_round_id = ?
            """,
            (
                transport_status,
                core_raw_round_id,
                error_code,
                _now(),
                raw_round_id,
            ),
        )
        return updated.rowcount == 1

    def clear_raw_round_payload(self, raw_round_id: str) -> bool:
        updated = self._connection.execute(
            """
            UPDATE raw_round_payloads
            SET payload_json = '{}', payload_bytes = 0, deleted_at = ?
            WHERE raw_round_id = ? AND deleted_at IS NULL
            """,
            (_now(), raw_round_id),
        )
        return updated.rowcount == 1

    def get_core_command(self, command_id: str) -> CoreCommandRecord | None:
        row = self._connection.execute(
            "SELECT * FROM core_commands WHERE command_id = ?", (command_id,)
        ).fetchone()
        return self._core_command_from_row(row) if row is not None else None

    def claim_core_command(
        self,
        *,
        worker_id: str,
        lease_seconds: float = 300,
        now: str | None = None,
    ) -> CoreCommandRecord | None:
        now_datetime = (
            datetime.fromisoformat(now)
            if now is not None
            else datetime.now(timezone.utc)
        )
        if now_datetime.tzinfo is None:
            now_datetime = now_datetime.replace(tzinfo=timezone.utc)
        now_value = now_datetime.isoformat(timespec="seconds")
        lease_expires_at = (
            now_datetime + timedelta(seconds=max(float(lease_seconds), 1))
        ).isoformat(timespec="seconds")
        row = self._connection.execute(
            """
            SELECT * FROM core_commands
            WHERE (
                status IN ('pending', 'retry_wait') AND available_at <= ?
            ) OR (
                status = 'delivering'
                AND lease_expires_at IS NOT NULL
                AND lease_expires_at <= ?
            )
            ORDER BY available_at, command_id
            LIMIT 1
            """,
            (now_value, now_value),
        ).fetchone()
        if row is None:
            return None
        updated = self._connection.execute(
            """
            UPDATE core_commands
            SET status = 'delivering', attempts = attempts + 1,
                lease_expires_at = ?, claimed_by = ?, completed_at = NULL
            WHERE command_id = ? AND (
                (status IN ('pending', 'retry_wait') AND available_at <= ?)
                OR (
                    status = 'delivering'
                    AND lease_expires_at IS NOT NULL
                    AND lease_expires_at <= ?
                )
            )
            """,
            (lease_expires_at, worker_id, row["command_id"], now_value, now_value),
        )
        if updated.rowcount != 1:
            return None
        claimed = self._connection.execute(
            "SELECT * FROM core_commands WHERE command_id = ?", (row["command_id"],)
        ).fetchone()
        return self._core_command_from_row(claimed) if claimed is not None else None

    def finish_core_command(
        self,
        command_id: str,
        *,
        worker_id: str,
        status: str,
        result_json: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        retry_delay_seconds: float = 0,
    ) -> bool:
        if status not in {"completed", "retry_wait", "rejected", "failed"}:
            raise ValueError(f"unsupported core command status: {status}")
        now_datetime = datetime.now(timezone.utc)
        now_value = now_datetime.isoformat(timespec="seconds")
        available_at = (
            now_datetime + timedelta(seconds=max(float(retry_delay_seconds), 0))
        ).isoformat(timespec="seconds")
        updated = self._connection.execute(
            """
            UPDATE core_commands
            SET status = ?,
                available_at = CASE WHEN ? = 'retry_wait' THEN ? ELSE available_at END,
                lease_expires_at = NULL,
                claimed_by = NULL,
                completed_at = CASE WHEN ? = 'retry_wait' THEN NULL ELSE ? END,
                result_json = COALESCE(?, result_json),
                last_error_code = ?,
                last_error_detail = ?
            WHERE command_id = ? AND status = 'delivering' AND claimed_by = ?
            """,
            (
                status,
                status,
                available_at,
                status,
                now_value,
                result_json,
                error_code,
                error_detail,
                command_id,
                worker_id,
            ),
        )
        return updated.rowcount == 1

    def purge_expired(self, *, now: str | None = None, limit: int = 100) -> int:
        """Clear expired payloads while preserving raw provenance and derivatives."""

        cutoff = now or _now()
        bounded_limit = max(int(limit), 1)
        rows = self._connection.execute(
            """
            SELECT raw_round_id
            FROM raw_round_payloads
            WHERE deleted_at IS NULL
              AND retention_expires_at IS NOT NULL
              AND retention_expires_at <= ?
            ORDER BY retention_expires_at ASC
            LIMIT ?
            """,
            (cutoff, bounded_limit),
        ).fetchall()
        deleted = 0
        for row in rows:
            result = self._connection.execute(
                """
                UPDATE raw_round_payloads
                SET payload_json = '{}', payload_bytes = 0, deleted_at = ?
                WHERE raw_round_id = ? AND deleted_at IS NULL
                """,
                (cutoff, row["raw_round_id"]),
            )
            deleted += max(result.rowcount, 0)
        return deleted

    def _round_from_row(self, row: sqlite3.Row) -> RawRoundRecord:
        return RawRoundRecord(
            raw_round_id=str(row["raw_round_id"]),
            memory_space_id=str(row["memory_space_id"]),
            source_system=str(row["source_system"]),
            source_instance_id=str(row["source_instance_id"]),
            source_profile_id=str(row["source_profile_id"]),
            source_session_id=str(row["source_session_id"]),
            source_round_id=str(row["source_round_id"]),
            source_round_key=str(row["source_round_key"]),
            capture_schema_version=int(row["capture_schema_version"]),
            adapter_version=str(row["adapter_version"]),
            payload_json=str(row["payload_json"]),
            payload_digest=str(row["payload_digest"]),
            started_at=str(row["started_at"]),
            completed_at=str(row["completed_at"]),
            received_at=str(row["received_at"]),
            retention_expires_at=row["retention_expires_at"],
        )

    @staticmethod
    def _core_command_from_row(row: sqlite3.Row) -> CoreCommandRecord:
        return CoreCommandRecord(
            command_id=str(row["command_id"]),
            command_type=str(row["command_type"]),
            memory_space_id=str(row["memory_space_id"]),
            idempotency_key=str(row["idempotency_key"]),
            payload_json=str(row["payload_json"]),
            payload_digest=str(row["payload_digest"]),
            status=str(row["status"]),
            attempts=int(row["attempts"]),
            available_at=str(row["available_at"]),
            lease_expires_at=row["lease_expires_at"],
            claimed_by=row["claimed_by"],
            completed_at=row["completed_at"],
            result_json=row["result_json"],
            last_error_code=row["last_error_code"],
            last_error_detail=row["last_error_detail"],
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _core_raw_round_delivery_from_row(
        row: sqlite3.Row,
    ) -> CoreRawRoundDeliveryRecord:
        return CoreRawRoundDeliveryRecord(
            raw_round_id=str(row["raw_round_id"]),
            memory_space_id=str(row["memory_space_id"]),
            command_id=str(row["command_id"]),
            idempotency_key=str(row["idempotency_key"]),
            transport_status=str(row["transport_status"]),
            core_raw_round_id=(
                str(row["core_raw_round_id"])
                if row["core_raw_round_id"] is not None
                else None
            ),
            last_error_code=(
                str(row["last_error_code"])
                if row["last_error_code"] is not None
                else None
            ),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
