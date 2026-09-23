"""One-time migration of persisted Local contract payloads.

SQL migration 0007 changes the schema and queued command name.  This module
rewrites the durable payloads while delivery is stopped, preserving the
source-round identity and all delivery state.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ledgermind_protocol import calculate_payload_digest

from .database import open_sqlite_connection

CONTRACT_MIGRATION_MARKER = "contract_payloads"
SQL_MIGRATION_MARKER = "contract_naming"


class ContractMigrationError(RuntimeError):
    """Base error for the Local contract migration."""


class ContractMigrationBackupError(ContractMigrationError):
    """The pre-migration SQLite backup could not be created or verified."""


class ContractMigrationPreconditionError(ContractMigrationError):
    """The database is not safe to migrate yet."""


@dataclass(frozen=True, slots=True)
class ContractMigrationResult:
    """Observable result of one contract migration attempt."""

    marker: str
    already_applied: bool
    migrated_rounds: int
    migrated_commands: int
    backup_path: Path | None
    delivery_stopped: bool


ConnectionFactory = Callable[[str | Path], sqlite3.Connection]
StopDelivery = Callable[[], object]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _marker_exists(connection: sqlite3.Connection, marker: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM contract_migration_markers WHERE marker = ?",
        (marker,),
    ).fetchone()
    return row is not None


def _json_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _schema_number(value: object) -> int:
    if isinstance(value, bool):
        raise ContractMigrationError("legacy schema version must be numeric")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    raise ContractMigrationError("legacy schema version is malformed")


def _migrate_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    result = json.loads(json.dumps(dict(payload), ensure_ascii=False))
    if not isinstance(result, dict):
        raise ContractMigrationError("RawRound payload must be an object")
    changed = False

    if "api_version" in result:
        legacy_version = result.pop("api_version")
        if "schema_version" not in result:
            result["schema_version"] = _schema_number(legacy_version)
        changed = True

    extensions = result.get("extensions")
    if isinstance(extensions, dict):
        legacy_context = extensions.pop("ledgermind_context_v1", None)
        if legacy_context is not None:
            current_context = extensions.get("ledgermind_context")
            if current_context is not None and current_context != legacy_context:
                raise ContractMigrationError(
                    "legacy and stable context extensions contain different values"
                )
            extensions["ledgermind_context"] = legacy_context
            changed = True

        context = extensions.get("ledgermind_context")
        if isinstance(context, dict):
            if "api_version" in context:
                legacy_context_version = context.pop("api_version")
                if "schema_version" not in context:
                    context["schema_version"] = _schema_number(legacy_context_version)
                changed = True
            if "schema_version" not in context:
                context["schema_version"] = 1
                changed = True

    return result, changed


def _backup_database(
    connection: sqlite3.Connection,
    *,
    database_path: str | Path | None,
    backup_path: str | Path | None,
) -> Path:
    if backup_path is not None:
        destination = Path(backup_path).expanduser()
    elif database_path is not None and str(database_path) != ":memory:":
        source = Path(database_path).expanduser()
        destination = source.with_name(
            f".{source.name}.contract-migration-{uuid.uuid4().hex}.db"
        )
    else:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".contract-migration-", suffix=".db"
        )
        os.close(descriptor)
        destination = Path(temporary_name)

    if destination.exists() and destination.stat().st_size > 0:
        raise ContractMigrationBackupError(f"backup destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        backup = sqlite3.connect(destination)
        try:
            connection.backup(backup)
            backup.commit()
            integrity = backup.execute("PRAGMA integrity_check").fetchone()
        finally:
            backup.close()
        if integrity is None or integrity[0] != "ok":
            raise ContractMigrationBackupError("contract migration backup failed integrity check")
        os.chmod(destination, 0o600)
        return destination
    except ContractMigrationBackupError:
        destination.unlink(missing_ok=True)
        raise
    except (OSError, sqlite3.DatabaseError) as exc:
        destination.unlink(missing_ok=True)
        raise ContractMigrationBackupError("contract migration backup failed") from exc


def _assert_preconditions(connection: sqlite3.Connection) -> None:
    active = connection.execute(
        """
        SELECT command_id
        FROM core_commands
        WHERE status = 'delivering'
        LIMIT 1
        """
    ).fetchone()
    if active is not None:
        raise ContractMigrationPreconditionError(
            "Core delivery still owns a leased command"
        )


def _update_command_metadata(
    connection: sqlite3.Connection,
    *,
    raw_round_id: str,
    payload_digest: str,
) -> int:
    delivery = connection.execute(
        """
        SELECT command_id
        FROM raw_round_core_deliveries
        WHERE raw_round_id = ?
        """,
        (raw_round_id,),
    ).fetchone()
    if delivery is None:
        return 0
    command_id = str(delivery[0])
    command = connection.execute(
        """
        SELECT memory_space_id, payload_json, payload_digest, idempotency_key
        FROM core_commands
        WHERE command_id = ?
        """,
        (command_id,),
    ).fetchone()
    if command is None:
        raise ContractMigrationError(
            f"delivery {raw_round_id} references missing command {command_id}"
        )
    try:
        command_payload = json.loads(str(command[1]))
    except json.JSONDecodeError as exc:
        raise ContractMigrationError(
            f"command {command_id} payload is not valid JSON"
        ) from exc
    if not isinstance(command_payload, dict):
        raise ContractMigrationError(f"command {command_id} payload must be an object")
    command_digest = _json_digest(command_payload)
    collision = connection.execute(
        """
        SELECT command_id
        FROM core_commands
        WHERE memory_space_id = ? AND idempotency_key = ? AND command_id != ?
        """,
        (str(command[0]), payload_digest, command_id),
    ).fetchone()
    if collision is not None:
        raise ContractMigrationPreconditionError(
            f"idempotency key conflicts with command {collision[0]}"
        )
    updated_commands = connection.execute(
        """
        UPDATE core_commands
        SET command_type = 'ingest_raw_round',
            idempotency_key = ?,
            payload_digest = ?
        WHERE command_id = ?
          AND (command_type != 'ingest_raw_round'
               OR idempotency_key != ?
               OR payload_digest != ?)
        """,
        (payload_digest, command_digest, command_id, payload_digest, command_digest),
    ).rowcount
    connection.execute(
        """
        UPDATE raw_round_core_deliveries
        SET idempotency_key = ?, updated_at = ?
        WHERE raw_round_id = ?
        """,
        (payload_digest, _now(), raw_round_id),
    )
    return max(updated_commands, 0)


def _migrate_rows(connection: sqlite3.Connection) -> tuple[int, int]:
    migrated_rounds = 0
    migrated_commands = 0
    rows = connection.execute(
        """
        SELECT raw_rounds.raw_round_id,
               raw_rounds.payload_json,
               raw_rounds.payload_digest,
               raw_round_payloads.payload_json,
               raw_round_payloads.deleted_at
        FROM raw_rounds
        LEFT JOIN raw_round_payloads
          ON raw_round_payloads.raw_round_id = raw_rounds.raw_round_id
        ORDER BY raw_rounds.raw_round_id
        """
    ).fetchall()
    for row in rows:
        raw_round_id = str(row[0])
        payload_text = str(row[3]) if row[3] is not None and row[4] is None else str(row[1])
        if not payload_text or payload_text == "{}":
            continue
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise ContractMigrationError(
                f"RawRound {raw_round_id} payload is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ContractMigrationError(f"RawRound {raw_round_id} payload must be an object")
        migrated_payload, payload_changed = _migrate_payload(payload)
        payload_digest = calculate_payload_digest(migrated_payload)
        serialized = json.dumps(
            migrated_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if payload_changed or str(row[2]) != payload_digest:
            if row[3] is not None and row[4] is None:
                connection.execute(
                    """
                    UPDATE raw_round_payloads
                    SET payload_json = ?, payload_bytes = ?
                    WHERE raw_round_id = ?
                    """,
                    (serialized, len(serialized.encode("utf-8")), raw_round_id),
                )
            else:
                connection.execute(
                    "UPDATE raw_rounds SET payload_json = ? WHERE raw_round_id = ?",
                    (serialized, raw_round_id),
                )
            connection.execute(
                "UPDATE raw_rounds SET payload_digest = ? WHERE raw_round_id = ?",
                (payload_digest, raw_round_id),
            )
            migrated_rounds += 1
        migrated_commands += _update_command_metadata(
            connection,
            raw_round_id=raw_round_id,
            payload_digest=payload_digest,
        )

    migrated_commands += max(
        connection.execute(
            """
            UPDATE core_commands
            SET command_type = 'ingest_raw_round'
            WHERE command_type = 'ingest_raw_round_v2'
            """
        ).rowcount,
        0,
    )
    return migrated_rounds, migrated_commands


def migrate_contract_payloads(
    database_path: str | Path | None = None,
    *,
    connection: sqlite3.Connection | None = None,
    backup_path: str | Path | None = None,
    stop_delivery: StopDelivery | None = None,
    connection_factory: ConnectionFactory = open_sqlite_connection,
) -> ContractMigrationResult:
    """Back up and migrate Local contract payloads exactly once.

    ``stop_delivery`` is called after the backup and before the migration
    transaction.  Local startup has not started workers yet, but accepting the
    hook makes the delivery boundary explicit for maintenance callers.
    """

    if connection is None and database_path is None:
        raise ValueError("database_path or connection is required")
    owns_connection = connection is None
    active_connection = connection or connection_factory(database_path or "")
    try:
        if not _table_exists(active_connection, "contract_migration_markers"):
            raise ContractMigrationPreconditionError(
                "Local schema 7 is required before contract migration"
            )
        if _marker_exists(active_connection, CONTRACT_MIGRATION_MARKER):
            return ContractMigrationResult(
                marker=CONTRACT_MIGRATION_MARKER,
                already_applied=True,
                migrated_rounds=0,
                migrated_commands=0,
                backup_path=None,
                delivery_stopped=False,
            )

        backup = _backup_database(
            active_connection,
            database_path=database_path,
            backup_path=backup_path,
        )
        if stop_delivery is not None:
            stop_delivery()
        _assert_preconditions(active_connection)
        if active_connection.in_transaction:
            active_connection.commit()
        active_connection.execute("BEGIN IMMEDIATE")
        try:
            migrated_rounds, migrated_commands = _migrate_rows(active_connection)
            active_connection.execute(
                """
                INSERT INTO contract_migration_markers (marker, applied_at)
                VALUES (?, ?)
                """,
                (CONTRACT_MIGRATION_MARKER, _now()),
            )
            active_connection.commit()
        except Exception:
            active_connection.rollback()
            raise
        return ContractMigrationResult(
            marker=CONTRACT_MIGRATION_MARKER,
            already_applied=False,
            migrated_rounds=migrated_rounds,
            migrated_commands=migrated_commands,
            backup_path=backup,
            delivery_stopped=stop_delivery is not None,
        )
    finally:
        if owns_connection:
            active_connection.close()


__all__ = [
    "CONTRACT_MIGRATION_MARKER",
    "ContractMigrationBackupError",
    "ContractMigrationError",
    "ContractMigrationPreconditionError",
    "ContractMigrationResult",
    "migrate_contract_payloads",
]
