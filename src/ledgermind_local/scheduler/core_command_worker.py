"""Durable delivery worker for Local-to-Core commands."""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ledgermind_local.core_gateway.base import CoreGateway
from ledgermind_local.core_gateway.contracts import (
    DomainRejectedError,
    IngestRawRoundCommand,
    IngestRawRoundResult,
    TransientCoreError,
)
from ledgermind_local.persistence import CoreCommandRecord, SQLiteUnitOfWork

from .guarded_loop import GuardedWorkerLoop
from .worker_state import WorkerState

_REDACT_INLINE = re.compile(
    r"(?i)(\b(?:api[_-]?key|secret|password|token|authorization|credential)\b\s*[:=]\s*)[^\s,;]+"
)
_REDACT_BEARER = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")


def _redact_text(value: str) -> str:
    value = _REDACT_INLINE.sub(r"\1[REDACTED]", value)
    return _REDACT_BEARER.sub(r"\1[REDACTED]", value)


@dataclass(frozen=True, slots=True)
class CoreCommandProcessResult:
    command_id: str
    status: str


class CoreCommandWorker:
    """Claim, deliver and finalize Core commands outside SQLite transactions."""

    def __init__(
        self,
        *,
        database_path: str | Path,
        gateway: CoreGateway,
        worker_id: str | None = None,
        max_attempts: int = 5,
        retry_delay_seconds: float = 30,
        lease_seconds: float = 300,
        state: WorkerState | None = None,
        embedding_profile_metadata_factory: Callable[[str], dict[str, object]] | None = None,
    ) -> None:
        self.database_path = database_path
        self.gateway = gateway
        self.worker_id = worker_id or str(uuid.uuid4())
        self.max_attempts = max(int(max_attempts), 1)
        self.retry_delay_seconds = max(float(retry_delay_seconds), 0)
        self.lease_seconds = max(float(lease_seconds), 1)
        self.state = state or WorkerState("core-command")
        self.embedding_profile_metadata_factory = embedding_profile_metadata_factory
        self._stop = threading.Event()
        self._loop: GuardedWorkerLoop | None = None

    def process_once(self) -> CoreCommandProcessResult | None:
        if self._stop.is_set():
            return None
        command = self._claim()
        if command is None:
            return None
        try:
            if command.command_type == "ingest_raw_round":
                raw_result = self._deliver_raw_round(command)
                if not raw_result.accepted:
                    raise DomainRejectedError(
                        "core_rejected", "Core did not accept RawRound"
                    )
                result_json = raw_result.result_json or json.dumps(
                    {
                        "accepted": raw_result.accepted,
                        "duplicate": raw_result.duplicate,
                        "raw_round_id": raw_result.core_raw_round_id,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                return self._finish(
                    command.command_id,
                    status="completed",
                    result_json=result_json,
                )
            if command.command_type != "ingest_raw_round":
                raise DomainRejectedError(
                    "unsupported_command_type",
                    command.command_type,
                )
        except DomainRejectedError as exc:
            return self._finish(
                command.command_id,
                status="rejected",
                error_code=exc.code,
                error_detail=_redact_text(exc.detail)[:2_000],
            )
        except (TransientCoreError, ValueError) as exc:
            return self._finish_retry_or_failure(
                command.command_id,
                attempts=command.attempts,
                error_code="core_delivery_error",
                error=exc,
            )
        except Exception as exc:  # noqa: BLE001
            return self._finish_retry_or_failure(
                command.command_id,
                attempts=command.attempts,
                error_code="core_gateway_error",
                error=exc,
            )
        return None

    def request_stop(self) -> None:
        self._stop.set()
        if self._loop is not None:
            self._loop.stop_event.set()

    def create_loop(
        self,
        *,
        poll_interval_seconds: float = 1.0,
        initial_backoff_seconds: float = 0.25,
        max_backoff_seconds: float = 30.0,
    ) -> GuardedWorkerLoop:
        loop = GuardedWorkerLoop(
            self,
            state=self.state,
            name="core-command",
            poll_interval_seconds=poll_interval_seconds,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )
        self._loop = loop
        if self._stop.is_set():
            loop.stop_event.set()
        return loop

    def run_loop(
        self,
        *,
        poll_interval_seconds: float = 1.0,
        initial_backoff_seconds: float = 0.25,
        max_backoff_seconds: float = 30.0,
    ) -> None:
        self.create_loop(
            poll_interval_seconds=poll_interval_seconds,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        ).run()

    def _claim(self) -> CoreCommandRecord | None:
        if self._stop.is_set():
            return None
        with SQLiteUnitOfWork(self.database_path, write_transaction=True) as uow:
            command = uow.raw_rounds.claim_core_command(
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            if command is None:
                return None
            uow.commit()
            return command

    def _deliver_raw_round(self, command: CoreCommandRecord) -> IngestRawRoundResult:
        try:
            metadata = json.loads(command.payload_json)
            raw_round_id = str(metadata["raw_round_id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DomainRejectedError(
                "invalid_raw_round_command", "RawRound command metadata is invalid"
            ) from exc
        with SQLiteUnitOfWork(self.database_path, write_transaction=False) as uow:
            raw_round = uow.raw_rounds.get(raw_round_id)
            if raw_round is None:
                raise DomainRejectedError("raw_round_not_found", raw_round_id)
            try:
                raw_payload = json.loads(raw_round.payload_json)
            except json.JSONDecodeError as exc:
                raise DomainRejectedError(
                    "invalid_raw_round_payload", "RawRound payload is not valid JSON"
                ) from exc
        if not isinstance(raw_payload, dict):
            raise DomainRejectedError(
                "invalid_raw_round_payload", "RawRound payload must be an object"
            )
        embedding_profile = None
        if self.embedding_profile_metadata_factory is not None:
            embedding_profile = self.embedding_profile_metadata_factory(command.memory_space_id)
        extensions = raw_payload.get("extensions")
        resolution_context = (
            dict(extensions["resolution_context"])
            if isinstance(extensions, dict)
            and isinstance(extensions.get("resolution_context"), dict)
            else None
        )
        return self.gateway.ingest_raw_round(
            IngestRawRoundCommand(
                command_id=command.command_id,
                idempotency_key=command.idempotency_key,
                memory_space_id=command.memory_space_id,
                raw_round_id=raw_round_id,
                raw_round=raw_payload,
                resolution_context=resolution_context,
                embedding_profile=embedding_profile,
            )
        )

    def _finish_retry_or_failure(
        self,
        command_id: str,
        *,
        attempts: int,
        error_code: str,
        error: Exception,
    ) -> CoreCommandProcessResult:
        status = "failed" if attempts >= self.max_attempts else "retry_wait"
        return self._finish(
            command_id,
            status=status,
            error_code=error_code,
            error_detail=_redact_text(str(error))[:2_000],
        )

    def _finish(
        self,
        command_id: str,
        *,
        status: str,
        result_json: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> CoreCommandProcessResult:
        with SQLiteUnitOfWork(self.database_path, write_transaction=True) as uow:
            command = uow.raw_rounds.get_core_command(command_id)
            if command is None:
                return CoreCommandProcessResult(command_id, "missing")
            updated = uow.raw_rounds.finish_core_command(
                command_id,
                worker_id=self.worker_id,
                status=status,
                result_json=result_json,
                error_code=error_code,
                error_detail=error_detail,
                retry_delay_seconds=self.retry_delay_seconds,
            )
            if not updated:
                uow.rollback()
                return CoreCommandProcessResult(command_id, "lease_lost")
            if command.command_type == "ingest_raw_round":
                try:
                    raw_round_id = str(json.loads(command.payload_json)["raw_round_id"])
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    raw_round_id = ""
                if raw_round_id:
                    delivery_status = {
                        "completed": "accepted",
                        "rejected": "rejected",
                        "retry_wait": "retry_wait",
                        "failed": "rejected",
                    }.get(status, "retry_wait")
                    core_raw_round_id: str | None = None
                    if result_json:
                        try:
                            result_payload = json.loads(result_json)
                            if isinstance(result_payload, dict):
                                core_raw_round_id = (
                                    str(result_payload["raw_round_id"])
                                    if result_payload.get("raw_round_id") is not None
                                    else None
                                )
                        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                            pass
                    uow.raw_rounds.update_core_raw_round_delivery(
                        raw_round_id,
                        transport_status=delivery_status,
                        core_raw_round_id=core_raw_round_id,
                        error_code=error_code,
                    )
                    if status == "completed":
                        uow.raw_rounds.clear_raw_round_payload(raw_round_id)
            uow.commit()
        return CoreCommandProcessResult(command_id, status)


__all__ = ["CoreCommandProcessResult", "CoreCommandWorker"]
