from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from ledgermind_local.core_gateway.maintenance import (
    BackupManifest,
    PrepareRestoreResult,
    sha256_file,
)
from ledgermind_local.core_gateway.compatibility import SUPPORTED_KNOWLEDGE_SCHEMA_MAX
from ledgermind_local.maintenance.core_backup import CoreBackupError, CoreBackupService
from ledgermind_local.persistence import rounds_migrations


class _Gateway:
    def __init__(self, core_data_dir: Path) -> None:
        self.core_data_dir = core_data_dir
        self.validation_commands = []
        self.prepare_commands = []

    def create_backup(self, command):
        source = self.core_data_dir / "exchange" / "outgoing" / "core-snapshot.bin"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"opaque-core-snapshot")
        return BackupManifest(
            relative_path="exchange/outgoing/core-snapshot.bin",
            sha256=sha256_file(source),
            size_bytes=source.stat().st_size,
        schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
        )

    def validate_backup(self, command):
        self.validation_commands.append(command)
        path = self.core_data_dir / command.relative_path
        return BackupManifest(
            relative_path=command.relative_path,
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
        schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
        )

    def prepare_restore(self, command):
        self.prepare_commands.append(command)
        path = self.core_data_dir / command.relative_path
        return PrepareRestoreResult(
            relative_path=command.relative_path,
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
        schema_version=SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
            restore_token="restore-token",
            requires_restart=True,
        )


def _rounds_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    rounds_migrations.apply_migrations(connection)
    connection.execute(
        "INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("space-1", "tests", "2026-08-04T00:00:00Z", "2026-08-04T00:00:00Z"),
    )
    connection.commit()
    connection.close()


def test_core_backup_round_trip_keeps_core_snapshot_opaque(tmp_path: Path) -> None:
    core_data_dir = tmp_path / "core"
    core_data_dir.mkdir(mode=0o700)
    rounds_database = tmp_path / "rounds.db"
    _rounds_database(rounds_database)
    gateway = _Gateway(core_data_dir)
    service = CoreBackupService(
        gateway=gateway,  # type: ignore[arg-type]
        core_data_dir=core_data_dir,
        rounds_database_path=rounds_database,
    )

    archive_path = service.create_backup(tmp_path / "backups")

    assert not (core_data_dir / "exchange/outgoing/core-snapshot.bin").exists()
    assert archive_path.stat().st_mode & 0o777 == 0o600
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert names == {
            "backup_manifest.json",
            "rounds.db",
            "core_snapshot/core-snapshot.bin",
        }
        assert "server.token" not in names
        assert "knowledge.db" not in names
        manifest = json.loads(archive.read("backup_manifest.json"))
        assert manifest["core"]["relative_path"] == "exchange/outgoing/core-snapshot.bin"
        assert archive.getinfo("core_snapshot/core-snapshot.bin").external_attr >> 16 & 0o777 == 0o600

    prepared = service.prepare_restore(archive_path)
    try:
        assert prepared.rounds_snapshot_path.is_file()
        assert prepared.restore_token == "restore-token"
        assert prepared.core_exchange_path.is_file()
        assert gateway.validation_commands[0].relative_path.startswith("exchange/incoming/")
        assert gateway.prepare_commands[0].relative_path == gateway.validation_commands[0].relative_path
        assert not (core_data_dir / "knowledge.db").exists()
    finally:
        incoming = prepared.core_exchange_path
        prepared.cleanup()
    assert not incoming.exists()
    assert not prepared.staging_dir.exists()


def test_core_backup_rejects_archive_path_traversal(tmp_path: Path) -> None:
    core_data_dir = tmp_path / "core"
    core_data_dir.mkdir(mode=0o700)
    rounds_database = tmp_path / "rounds.db"
    _rounds_database(rounds_database)
    archive_path = tmp_path / "unsafe.zip"
    payload = {
        "format": "ledgermind-local-core-backup",
        "schema_version": 1,
        "core": {
            "relative_path": "exchange/outgoing/../escape.bin",
            "sha256": "sha256:" + "a" * 64,
            "size_bytes": 1,
            "schema_version": 5,
        },
        "core_archive_member": "core_snapshot/escape.bin",
        "rounds_archive_member": "rounds.db",
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("backup_manifest.json", json.dumps(payload))
        archive.writestr("rounds.db", b"not sqlite")
        archive.writestr("core_snapshot/escape.bin", b"x")

    service = CoreBackupService(
        gateway=_Gateway(core_data_dir),  # type: ignore[arg-type]
        core_data_dir=core_data_dir,
        rounds_database_path=rounds_database,
    )

    with pytest.raises(RuntimeError, match="backup"):
        service.prepare_restore(archive_path)


def test_core_backup_reports_missing_core_data_dir(tmp_path: Path) -> None:
    archive_path = tmp_path / "backup.zip"
    archive_path.write_bytes(b"not a zip")
    service = CoreBackupService(
        gateway=_Gateway(tmp_path / "missing-core"),  # type: ignore[arg-type]
        core_data_dir=tmp_path / "missing-core",
        rounds_database_path=tmp_path / "rounds.db",
    )

    with pytest.raises(CoreBackupError, match="Core data directory is missing"):
        service.prepare_restore(archive_path)
