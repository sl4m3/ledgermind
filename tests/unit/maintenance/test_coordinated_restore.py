from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ledgermind_local.core_gateway.maintenance import (
    BackupManifest,
    BeginRestoreResult,
    CommitRestoreResult,
    PrepareRestoreResult,
    RollbackRestoreResult,
    sha256_file,
)
from ledgermind_local.core_gateway.compatibility import SUPPORTED_KNOWLEDGE_SCHEMA_MAX
from ledgermind_local.maintenance.coordinated_restore import (
    CoordinatedRestoreError,
    CoordinatedRestoreService,
)
from ledgermind_local.maintenance.core_backup import CoreBackupService


class FakeCoreGateway:
    def __init__(self, core_data_dir: Path, *, fail_commit: bool = False) -> None:
        self.core_data_dir = core_data_dir
        self.fail_commit = fail_commit
        self.calls: list[str] = []
        self.core_data_dir.joinpath("exchange/outgoing").mkdir(parents=True)
        self.core_data_dir.joinpath("exchange/incoming").mkdir(parents=True)
        source = self.core_data_dir / "exchange/outgoing/core.bin"
        source.write_bytes(b"opaque-core-snapshot")
        self.transaction_id = "transaction-1"

    def require_capabilities(self, *capabilities: str) -> None:
        assert set(capabilities) == {"maintenance"}

    def create_backup(self, command: object) -> BackupManifest:
        del command
        source = self.core_data_dir / "exchange/outgoing/core.bin"
        return BackupManifest(
            relative_path="exchange/outgoing/core.bin",
            sha256=sha256_file(source),
            size_bytes=source.stat().st_size,
            schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
        )

    def validate_backup(self, command: object) -> BackupManifest:
        path = self.core_data_dir / command.relative_path  # type: ignore[attr-defined]
        return BackupManifest(
            relative_path=command.relative_path,  # type: ignore[attr-defined]
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
            schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
        )

    def prepare_restore(self, command: object) -> PrepareRestoreResult:
        self.calls.append("prepare")
        path = self.core_data_dir / command.relative_path  # type: ignore[attr-defined]
        return PrepareRestoreResult(
            relative_path=command.relative_path,  # type: ignore[attr-defined]
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
            schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
            restore_token="restore-token-1",
            requires_restart=True,
        )

    def begin_restore(self, command: object) -> BeginRestoreResult:
        self.calls.append("begin")
        return BeginRestoreResult(
            restore_transaction_id=self.transaction_id,
            relative_path=command.relative_path,  # type: ignore[attr-defined]
            sha256=command.sha256,  # type: ignore[attr-defined]
            size_bytes=20,
            schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
            state="applied_pending_commit",
        )

    def commit_restore(self, command: object) -> CommitRestoreResult:
        self.calls.append("commit")
        if self.fail_commit:
            raise RuntimeError("commit failed")
        return CommitRestoreResult(
            restore_transaction_id=command.restore_transaction_id,  # type: ignore[attr-defined]
            committed=True,
            state="committed",
        )

    def rollback_restore(self, command: object) -> RollbackRestoreResult:
        self.calls.append("rollback")
        return RollbackRestoreResult(
            restore_transaction_id=command.restore_transaction_id,  # type: ignore[attr-defined]
            rolled_back=True,
            state="rolled_back",
        )


def _rounds_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table VALUES ('before')")
        connection.commit()
    finally:
        connection.close()


def _round_value(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT value FROM values_table").fetchone()[0]
    finally:
        connection.close()


def _service(tmp_path: Path, *, fail_commit: bool = False):
    core_data_dir = tmp_path / "core"
    rounds = tmp_path / "rounds.db"
    _rounds_database(rounds)
    gateway = FakeCoreGateway(core_data_dir, fail_commit=fail_commit)
    backup_service = CoreBackupService(
        gateway=gateway,
        core_data_dir=core_data_dir,
        rounds_database_path=rounds,
    )
    journal_path = tmp_path / "restore-journal.json"
    lifecycle: list[str] = []
    saga = CoordinatedRestoreService(
        core_backup_service=backup_service,
        rounds_database_path=rounds,
        journal_path=journal_path,
        stop_core=lambda: lifecycle.append("stop"),
        start_core=lambda: lifecycle.append("start"),
        health_check=lambda: True,
    )
    archive = tmp_path / "backup.zip"
    backup_service.create_backup(archive)
    connection = sqlite3.connect(rounds)
    try:
        connection.execute("UPDATE values_table SET value = 'after'")
        connection.commit()
    finally:
        connection.close()
    return saga, archive, rounds, gateway, lifecycle, journal_path


def test_coordinated_restore_restores_rounds_and_cleans_journal(tmp_path: Path) -> None:
    saga, archive, rounds, gateway, lifecycle, journal_path = _service(tmp_path)

    prepared = saga.prepare_restore(archive)
    assert prepared.journal.core_restore_token == "restore-token-1"
    assert journal_path.exists()
    result = saga.apply_restore(prepared)

    assert result.state == "committed"
    assert _round_value(rounds) == "before"
    assert gateway.calls == ["prepare", "begin", "commit"]
    assert lifecycle == ["stop", "start"]
    assert not journal_path.exists()
    assert not prepared.rounds_rollback_path.exists()


def test_commit_failure_rolls_back_core_and_rounds(tmp_path: Path) -> None:
    saga, archive, rounds, gateway, lifecycle, journal_path = _service(
        tmp_path, fail_commit=True
    )

    prepared = saga.prepare_restore(archive)
    with pytest.raises(CoordinatedRestoreError) as error:
        saga.apply_restore(prepared)

    assert error.value.code == "restore_commit_failed"
    assert _round_value(rounds) == "after"
    assert gateway.calls == ["prepare", "begin", "commit", "rollback"]
    assert lifecycle == ["stop", "start", "stop", "start"]
    assert not journal_path.exists()


def test_corrupt_or_traversing_archive_is_rejected_before_journal(tmp_path: Path) -> None:
    saga, archive, _rounds, _gateway, _lifecycle, journal_path = _service(tmp_path)
    archive.write_bytes(b"not-a-zip")

    with pytest.raises(CoordinatedRestoreError):
        saga.prepare_restore(archive)
    assert not journal_path.exists()


def test_begin_pending_journal_is_recovered_by_idempotent_begin(tmp_path: Path) -> None:
    saga, archive, rounds, gateway, _lifecycle, journal_path = _service(tmp_path)
    prepared = saga.prepare_restore(archive)
    saga._write_journal(prepared.journal.with_state("begin_pending"))

    result = saga.recover()

    assert result is not None
    assert result.state == "rolled_back"
    assert _round_value(rounds) == "after"
    assert gateway.calls == ["prepare", "begin", "rollback"]
    assert not journal_path.exists()


def test_corrupt_journal_path_is_rejected_without_touching_rounds(tmp_path: Path) -> None:
    saga, archive, rounds, _gateway, _lifecycle, journal_path = _service(tmp_path)
    prepared = saga.prepare_restore(archive)
    payload = prepared.journal.to_payload()
    payload["rounds_rollback_path"] = str(tmp_path / ".." / "outside.sqlite")
    journal_path.write_text(__import__("json").dumps(payload), encoding="utf-8")

    with pytest.raises(CoordinatedRestoreError) as error:
        saga.recover()

    assert error.value.code == "restore_journal_corrupt"
    assert _round_value(rounds) == "after"
