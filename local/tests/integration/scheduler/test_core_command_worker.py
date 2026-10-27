from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ledgermind_local.core_gateway.contracts import (
    DomainRejectedError,
    IngestRawRoundResult,
    TransientCoreError,
)
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations as migrations
from ledgermind_local.persistence.raw_round_repository import SQLiteRawRoundRepository
from ledgermind_local.scheduler.core_command_worker import CoreCommandWorker


def _bootstrap(path: Path) -> tuple[sqlite3.Connection, SQLiteRawRoundRepository]:
    connection = open_sqlite_connection(path)
    migrations.apply_migrations(connection)
    connection.execute(
        """
        INSERT INTO memory_spaces (
            memory_space_id, display_name, source_client, created_at, updated_at
        ) VALUES ('space-1', 'Test space', 'test',
                  '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """
    )
    repository = SQLiteRawRoundRepository(connection)
    repository.insert(
        raw_round_id="raw-round-1",
        memory_space_id="space-1",
        source_system="hermes",
        source_instance_id="instance-1",
        source_profile_id="profile-1",
        source_session_id="session-1",
        source_round_id="round-1",
        source_round_key="source-key-1",
        capture_schema_version=1,
        adapter_version="test/1",
        payload_json='{"round":{"events":[]}}',
        payload_digest="sha256:" + "a" * 64,
        started_at="2026-08-03T00:00:00+00:00",
        completed_at="2026-08-03T00:01:00+00:00",
    )
    _queue_command(repository)
    connection.commit()
    return connection, repository


def _queue_command(repository: SQLiteRawRoundRepository, command_id: str = "command-1") -> None:
    repository.create_core_command(
        command_id=command_id,
        command_type="ingest_raw_round",
        memory_space_id="space-1",
        idempotency_key="sha256:" + command_id[-1] * 64,
        payload_json=json.dumps(
            {"raw_round_id": "raw-round-1"},
            sort_keys=True,
            separators=(",", ":"),
        ),
        payload_digest="sha256:" + "c" * 64,
        available_at="2026-08-03T00:00:00+00:00",
    )
    repository.create_core_raw_round_delivery(
        raw_round_id="raw-round-1",
        memory_space_id="space-1",
        command_id=command_id,
        idempotency_key="sha256:" + command_id[-1] * 64,
    )


class _Gateway:
    def __init__(self, outcomes: tuple[object, ...] = ()) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[str] = []
        self.commands: list[object] = []

    def ingest_raw_round(self, command) -> IngestRawRoundResult:
        self.calls.append(command.command_id)
        self.commands.append(command)
        outcome = self.outcomes.pop(0) if self.outcomes else IngestRawRoundResult(
            accepted=True,
            duplicate=False,
            core_raw_round_id="core-raw-1",
        )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_core_command_worker_delivers_raw_round_and_clears_payload(tmp_path: Path) -> None:
    connection, _ = _bootstrap(tmp_path / "rounds.db")
    connection.close()

    gateway = _Gateway()
    result = CoreCommandWorker(
        database_path=tmp_path / "rounds.db",
        gateway=gateway,
        worker_id="core-worker-1",
    ).process_once()

    assert result is not None
    assert result.status == "completed"
    assert gateway.calls == ["command-1"]
    with sqlite3.connect(tmp_path / "rounds.db") as check:
        assert check.execute(
            "SELECT transport_status, core_raw_round_id FROM raw_round_core_deliveries"
        ).fetchone() == ("accepted", "core-raw-1")
        assert check.execute(
            "SELECT payload_json, payload_bytes FROM raw_round_payloads"
        ).fetchone() == ("{}", 0)


def test_core_command_worker_forwards_embedding_identity_to_gateway(tmp_path: Path) -> None:
    connection, _ = _bootstrap(tmp_path / "rounds.db")
    connection.close()
    profile = {
        "embedding_model_id": "embedder",
        "embedding_model_version": "sha256:" + "a" * 64,
        "embedding_profile_fingerprint": "sha256:" + "a" * 64,
        "embedding_profile_model_version": "api:embedder",
        "embedding_profile_digest_algorithm": "sha256",
        "embedding_profile_digest_algorithm_schema_version": 1,
        "embedding_dimensions": 3,
    }
    gateway = _Gateway()
    result = CoreCommandWorker(
        database_path=tmp_path / "rounds.db",
        gateway=gateway,
        worker_id="core-worker-1",
        embedding_profile_metadata_factory=lambda _memory_space_id: profile,
    ).process_once()

    assert result is not None and result.status == "completed"
    assert gateway.commands[0].embedding_profile == profile


def test_core_command_worker_retries_transient_error_and_then_completes(
    tmp_path: Path,
) -> None:
    connection, _ = _bootstrap(tmp_path / "rounds.db")
    connection.close()
    gateway = _Gateway(
        (
            TransientCoreError("core unavailable"),
            IngestRawRoundResult(
                accepted=True,
                duplicate=True,
                core_raw_round_id="core-raw-1",
            ),
        )
    )
    worker = CoreCommandWorker(
        database_path=tmp_path / "rounds.db",
        gateway=gateway,
        worker_id="core-worker-1",
        retry_delay_seconds=0,
    )

    first = worker.process_once()
    second = worker.process_once()

    assert first is not None and first.status == "retry_wait"
    assert second is not None and second.status == "completed"
    assert gateway.calls == ["command-1", "command-1"]


def test_core_command_worker_rejects_domain_error_without_retry(
    tmp_path: Path,
) -> None:
    connection, _ = _bootstrap(tmp_path / "rounds.db")
    connection.close()
    worker = CoreCommandWorker(
        database_path=tmp_path / "rounds.db",
        gateway=_Gateway((DomainRejectedError("invalid_raw_round", "rejected"),)),
        worker_id="core-worker-1",
    )

    result = worker.process_once()
    again = worker.process_once()

    assert result is not None and result.status == "rejected"
    assert again is None
    with sqlite3.connect(tmp_path / "rounds.db") as check:
        assert check.execute(
            "SELECT status, last_error_code FROM core_commands"
        ).fetchone() == ("rejected", "invalid_raw_round")


def test_core_command_worker_reclaims_expired_delivery(tmp_path: Path) -> None:
    connection, repository = _bootstrap(tmp_path / "rounds.db")
    claimed = repository.claim_core_command(
        worker_id="crashed-worker",
        lease_seconds=30,
        now="2026-08-03T00:00:00+00:00",
    )
    assert claimed is not None
    connection.execute(
        "UPDATE core_commands SET lease_expires_at = ? WHERE command_id = ?",
        ("2020-01-01T00:00:00+00:00", claimed.command_id),
    )
    connection.commit()
    connection.close()

    result = CoreCommandWorker(
        database_path=tmp_path / "rounds.db",
        gateway=_Gateway(),
        worker_id="recovery-worker",
    ).process_once()

    assert result is not None and result.status == "completed"


def test_core_command_worker_request_stop_stops_created_loop(tmp_path: Path) -> None:
    connection, _ = _bootstrap(tmp_path / "stop.db")
    connection.close()
    worker = CoreCommandWorker(
        database_path=tmp_path / "stop.db",
        gateway=_Gateway(),
        worker_id="core-worker-1",
    )
    loop = worker.create_loop(poll_interval_seconds=0.01)
    loop.start()
    worker.request_stop()
    assert loop.join(timeout=1) is True
