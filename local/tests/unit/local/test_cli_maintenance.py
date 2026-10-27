"""Tests for maintenance CLI commands."""

from __future__ import annotations

import json
import os
import sqlite3
import zipfile
from pathlib import Path

import pytest

import ledgermind_local.cli as cli_module
from ledgermind_local.cli import main
from ledgermind_local.core_gateway.maintenance import (
    BackupManifest,
    BeginRestoreResult,
    CommitRestoreResult,
    PrepareRestoreResult,
    RollbackRestoreResult,
    sha256_file,
)
from ledgermind_local.core_gateway.compatibility import SUPPORTED_KNOWLEDGE_SCHEMA_MAX
from ledgermind_local.maintenance.core_backup import CoreBackupService
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations as migrations


class _CliCoreGateway:
    def __init__(self, core_data_dir: Path) -> None:
        self.core_data_dir = core_data_dir
        self.core_data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def require_capabilities(self, *capabilities: str) -> None:
        del capabilities

    def create_backup(self, command: object) -> BackupManifest:
        del command
        source = self.core_data_dir / "exchange" / "outgoing" / "core-snapshot.bin"
        source.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        source.write_bytes(b"opaque-core-snapshot")
        return BackupManifest(
            relative_path="exchange/outgoing/core-snapshot.bin",
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
        path = self.core_data_dir / command.relative_path  # type: ignore[attr-defined]
        return PrepareRestoreResult(
            relative_path=command.relative_path,  # type: ignore[attr-defined]
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
            schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
            restore_token="test-restore-token",
            requires_restart=True,
        )

    def begin_restore(self, command: object) -> BeginRestoreResult:
        return BeginRestoreResult(
            restore_transaction_id="transaction-1",
            relative_path=command.relative_path,  # type: ignore[attr-defined]
            sha256=command.sha256,  # type: ignore[attr-defined]
            size_bytes=20,
            schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
            state="applied_pending_commit",
        )

    def commit_restore(self, command: object) -> CommitRestoreResult:
        return CommitRestoreResult(
            restore_transaction_id=command.restore_transaction_id,  # type: ignore[attr-defined]
            committed=True,
            state="committed",
        )

    def rollback_restore(self, command: object) -> RollbackRestoreResult:
        return RollbackRestoreResult(
            restore_transaction_id=command.restore_transaction_id,  # type: ignore[attr-defined]
            rolled_back=True,
            state="rolled_back",
        )

    def start(self) -> None:
        return None

    def health(self) -> object:
        return True

    def close(self) -> None:
        return None


def _patch_core_backup(monkeypatch) -> None:
    def _build(*, paths, config):
        gateway = _CliCoreGateway(paths.core_data_dir)
        service = CoreBackupService(
            gateway=gateway,  # type: ignore[arg-type]
            core_data_dir=paths.core_data_dir,
            rounds_database_path=paths.resolve_rounds_database_path(
                config.rounds_database_path
            ),
        )
        return gateway, service

    monkeypatch.setattr(cli_module, "_build_core_backup_service", _build)



def test_rotate_token_updates_existing_token(tmp_path: Path) -> None:
    home = tmp_path / "service"
    assert main(["--home", str(home), "init", "--semantic-language", "ru"]) == 0
    old_token = (home / "server.token").read_text(encoding="utf-8")

    assert main(["--home", str(home), "rotate-token"]) == 0

    new_token = (home / "server.token").read_text(encoding="utf-8")
    assert new_token != old_token


def test_rotate_token_reports_error_when_service_layout_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "service"

    import ledgermind_local.cli as cli_module

    def _fail(_: object = None, **_kwargs: object) -> None:
        raise RuntimeError("simulated initialize failure")

    monkeypatch.setattr(cli_module, "initialize_local_layout", _fail)
    assert main(["--home", str(home), "rotate-token"]) == 1


def test_backup_create_writes_zip_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_core_backup(monkeypatch)
    home = tmp_path / "service"
    assert main(["--home", str(home), "init", "--semantic-language", "ru"]) == 0

    assert main(["--home", str(home), "backup", "create"]) == 0

    backup_dir = home / "backups"
    archives = sorted(backup_dir.glob("ledgermind-core-backup-*.zip"))
    assert archives
    with zipfile.ZipFile(archives[0], "r") as archive:
        names = set(archive.namelist())
    assert names == {
        "backup_manifest.json",
        "rounds.db",
        "core_snapshot/core-snapshot.bin",
    }


def test_backup_create_writes_to_requested_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_core_backup(monkeypatch)
    home = tmp_path / "service"
    assert main(["--home", str(home), "init", "--semantic-language", "ru"]) == 0

    target = home / "snapshot.zip"
    assert (
        main(["--home", str(home), "backup", "create", "--destination", str(target)])
        == 0
    )
    assert target.exists()


def test_backup_restore_keeps_core_snapshot_opaque(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_core_backup(monkeypatch)
    home = tmp_path / "service"
    assert main(["--home", str(home), "init", "--semantic-language", "ru"]) == 0

    backup = home / "snapshot.zip"
    assert (
        main(["--home", str(home), "backup", "create", "--destination", str(backup)])
        == 0
    )
    with zipfile.ZipFile(backup, "r") as archive:
        names = set(archive.namelist())
    assert "core_snapshot/core-snapshot.bin" in names
    assert "knowledge.db" not in names
    assert "server.token" not in names

    assert (
        main(["--home", str(home), "backup", "restore", "--source", str(backup)]) == 0
    )
    assert not (home / "knowledge.db").exists()


def test_backup_restore_reverts_database_to_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_core_backup(monkeypatch)
    home = tmp_path / "service"
    assert main(["--home", str(home), "init", "--semantic-language", "ru"]) == 0

    database = home / "rounds.db"
    connection = open_sqlite_connection(database)
    try:
        migrations.apply_migrations(connection)
        connection.execute(
            """
            INSERT OR IGNORE INTO memory_spaces (
                memory_space_id,
                display_name,
                source_client,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "space-a",
                "space A",
                "hermes",
                "2026-08-01T00:00:00+00:00",
                "2026-08-01T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    backup = home / "snapshot.zip"
    assert (
        main(["--home", str(home), "backup", "create", "--destination", str(backup)])
        == 0
    )

    connection = sqlite3.connect(database)
    try:
        connection.execute("DELETE FROM memory_spaces")
        connection.commit()
    finally:
        connection.close()

    assert (
        main(["--home", str(home), "backup", "restore", "--source", str(backup)]) == 0
    )

    connection = sqlite3.connect(database)
    try:
        rows = list(
            connection.execute(
                "SELECT memory_space_id FROM memory_spaces ORDER BY memory_space_id"
            ).fetchall()
        )
    finally:
        connection.close()
    assert rows == [("space-a",)]


def test_backup_restore_fails_when_service_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_core_backup(monkeypatch)
    home = tmp_path / "service"
    assert main(["--home", str(home), "init", "--semantic-language", "ru"]) == 0

    backup = home / "snapshot.zip"
    assert (
        main(["--home", str(home), "backup", "create", "--destination", str(backup)])
        == 0
    )

    lock_path = home / "service.lock"
    lock_path.write_text(
        json.dumps({"version": 1, "pid": os.getpid()}, sort_keys=True),
        encoding="utf-8",
    )

    assert (
        main(["--home", str(home), "backup", "restore", "--source", str(backup)]) == 1
    )
