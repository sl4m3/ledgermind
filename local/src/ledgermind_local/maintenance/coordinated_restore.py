"""Failure-safe coordinated restore for the Local rounds database and Core.

The service deliberately treats the Core snapshot as an opaque exchange
artifact.  It never opens, replaces, or otherwise owns Core's knowledge.db;
all Core mutations go through the Core gateway's restore IPC operations.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ledgermind_local.core_gateway.maintenance import (
    BeginRestoreCommand,
    BeginRestoreResult,
    CommitRestoreCommand,
    CommitRestoreResult,
    PrepareRestoreResult,
    RollbackRestoreCommand,
    RollbackRestoreResult,
)

from .core_backup import (
    CoreBackupService,
    PreparedCoreRestore,
    _atomic_copy,
    _sqlite_backup,
)

JOURNAL_VERSION = 1
_TERMINAL_STATES = frozenset({"committed", "rolled_back"})


class CoordinatedRestoreError(RuntimeError):
    """A coordinated restore failed and carries a safe machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        restore_id: str | None = None,
        inconsistent: bool = False,
        compensated: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.restore_id = restore_id
        self.inconsistent = inconsistent
        self.compensated = compensated


@dataclass(frozen=True, slots=True)
class RestoreJournal:
    """Durable saga state containing identifiers and paths, never user data."""

    restore_id: str
    state: str
    backup_id: str
    rounds_rollback_path: Path
    core_restore_token: str
    core_restore_transaction_id: str | None
    core_relative_path: str
    core_sha256: str
    core_size_bytes: int
    core_schema_version: int
    rounds_snapshot_path: Path
    core_exchange_path: Path
    staging_dir: Path

    def to_payload(self) -> dict[str, object]:
        return {
            "journal_version": JOURNAL_VERSION,
            "restore_id": self.restore_id,
            "state": self.state,
            "backup_id": self.backup_id,
            "rounds_rollback_path": str(self.rounds_rollback_path),
            "core_restore_token": self.core_restore_token,
            "core_restore_transaction_id": self.core_restore_transaction_id,
            "core_relative_path": self.core_relative_path,
            "core_sha256": self.core_sha256,
            "core_size_bytes": self.core_size_bytes,
            "core_schema_version": self.core_schema_version,
            "rounds_snapshot_path": str(self.rounds_snapshot_path),
            "core_exchange_path": str(self.core_exchange_path),
            "staging_dir": str(self.staging_dir),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RestoreJournal:
        allowed = {
            "journal_version",
            "restore_id",
            "state",
            "backup_id",
            "rounds_rollback_path",
            "core_restore_token",
            "core_restore_transaction_id",
            "core_relative_path",
            "core_sha256",
            "core_size_bytes",
            "core_schema_version",
            "rounds_snapshot_path",
            "core_exchange_path",
            "staging_dir",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise CoordinatedRestoreError(
                "restore_journal_corrupt",
                f"restore journal has unknown fields: {sorted(unknown)}",
            )
        if payload.get("journal_version") != JOURNAL_VERSION:
            raise CoordinatedRestoreError("restore_journal_corrupt", "unsupported restore journal")
        restore_id = _safe_identifier(payload.get("restore_id"), "restore_id")
        state = _required_text(payload.get("state"), "state")
        backup_id = _safe_identifier(payload.get("backup_id"), "backup_id")
        token = _safe_identifier(payload.get("core_restore_token"), "core_restore_token")
        transaction_id = payload.get("core_restore_transaction_id")
        if transaction_id is not None:
            transaction_id = _safe_identifier(transaction_id, "core_restore_transaction_id")
        relative_path = _safe_exchange_path(payload.get("core_relative_path"))
        core_sha256 = _required_text(payload.get("core_sha256"), "core_sha256")
        size_bytes = payload.get("core_size_bytes")
        schema_version = payload.get("core_schema_version")
        if (
            isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
            or isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version <= 0
        ):
            raise CoordinatedRestoreError("restore_journal_corrupt", "invalid Core manifest metadata")
        paths = {
            name: _journal_path(payload.get(name), name)
            for name in (
                "rounds_rollback_path",
                "rounds_snapshot_path",
                "core_exchange_path",
                "staging_dir",
            )
        }
        return cls(
            restore_id=restore_id,
            state=state,
            backup_id=backup_id,
            rounds_rollback_path=paths["rounds_rollback_path"],
            core_restore_token=token,
            core_restore_transaction_id=transaction_id,
            core_relative_path=relative_path,
            core_sha256=core_sha256,
            core_size_bytes=size_bytes,
            core_schema_version=schema_version,
            rounds_snapshot_path=paths["rounds_snapshot_path"],
            core_exchange_path=paths["core_exchange_path"],
            staging_dir=paths["staging_dir"],
        )

    def with_state(self, state: str, *, transaction_id: str | None = None) -> RestoreJournal:
        return RestoreJournal(
            restore_id=self.restore_id,
            state=state,
            backup_id=self.backup_id,
            rounds_rollback_path=self.rounds_rollback_path,
            core_restore_token=self.core_restore_token,
            core_restore_transaction_id=(
                self.core_restore_transaction_id if transaction_id is None else transaction_id
            ),
            core_relative_path=self.core_relative_path,
            core_sha256=self.core_sha256,
            core_size_bytes=self.core_size_bytes,
            core_schema_version=self.core_schema_version,
            rounds_snapshot_path=self.rounds_snapshot_path,
            core_exchange_path=self.core_exchange_path,
            staging_dir=self.staging_dir,
        )


@dataclass(frozen=True, slots=True)
class PreparedCoordinatedRestore:
    journal: RestoreJournal
    prepared_core: PreparedCoreRestore

    @property
    def restore_id(self) -> str:
        return self.journal.restore_id

    @property
    def rounds_rollback_path(self) -> Path:
        return self.journal.rounds_rollback_path

    @property
    def core_restore_transaction_id(self) -> str | None:
        return self.journal.core_restore_transaction_id

    @property
    def core_restore_token(self) -> str:
        return self.journal.core_restore_token

    @property
    def preparation(self) -> PrepareRestoreResult:
        return self.prepared_core.preparation


LifecycleCallback = Callable[[], object]


class CoordinatedRestoreService:
    """Run a journaled, compensating restore across Core and Local rounds."""

    def __init__(
        self,
        *,
        core_backup_service: CoreBackupService,
        rounds_database_path: str | Path,
        journal_path: str | Path | None = None,
        stop_core: LifecycleCallback | None = None,
        start_core: LifecycleCallback | None = None,
        health_check: LifecycleCallback | None = None,
    ) -> None:
        self.core_backup_service = core_backup_service
        self.rounds_database_path = Path(rounds_database_path).expanduser()
        self.journal_path = Path(journal_path or self.rounds_database_path.with_name("restore-journal.json"))
        self.journal_path = self.journal_path.expanduser()
        self.stop_core = stop_core or (lambda: None)
        self.start_core = start_core or (lambda: None)
        self.health_check = health_check or (lambda: True)
        self._completed_results: dict[str, CoordinatedRestoreResult] = {}
        self.journal_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.journal_path.parent, 0o700)
        self._rollback_root = self.journal_path.parent / ".restore-rollback"
        self._rollback_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self._rollback_root, 0o700)
        self._assert_local_ownership_boundary()

    def _assert_local_ownership_boundary(self) -> None:
        rounds = self.rounds_database_path.resolve()
        journal = self.journal_path.resolve()
        core_root = self.core_backup_service.core_data_dir.resolve()
        for name, path in (("rounds database", rounds), ("restore journal", journal)):
            try:
                path.relative_to(core_root)
            except ValueError:
                continue
            raise ValueError(f"Local {name} must not be inside Core data directory")

    def prepare_restore(self, archive_path: str | Path) -> PreparedCoordinatedRestore:
        """Prepare both sides and durably record the compensating Local snapshot."""

        existing = self._read_journal_or_none()
        if existing is not None:
            if existing.state == "restore_inconsistent":
                raise CoordinatedRestoreError(
                    "restore_inconsistent",
                    "a previous restore is inconsistent and blocks readiness",
                    restore_id=existing.restore_id,
                    inconsistent=True,
                )
            return self._prepared_from_journal(existing)

        restore_id = uuid.uuid4().hex
        prepared_core: PreparedCoreRestore | None = None
        rollback_path = self._rollback_root / f"{restore_id}.sqlite"
        try:
            prepared_core = self.core_backup_service.prepare_restore(archive_path)
            _sqlite_backup(self.rounds_database_path, rollback_path)
            journal = RestoreJournal(
                restore_id=restore_id,
                state="prepared",
                backup_id=prepared_core.preparation.sha256,
                rounds_rollback_path=rollback_path,
                core_restore_token=prepared_core.preparation.restore_token,
                core_restore_transaction_id=None,
                core_relative_path=prepared_core.preparation.relative_path,
                core_sha256=prepared_core.preparation.sha256,
                core_size_bytes=prepared_core.preparation.size_bytes,
                core_schema_version=prepared_core.preparation.schema_version,
                rounds_snapshot_path=prepared_core.rounds_snapshot_path,
                core_exchange_path=prepared_core.core_exchange_path,
                staging_dir=prepared_core.staging_dir,
            )
            self._write_journal(journal)
            return PreparedCoordinatedRestore(journal=journal, prepared_core=prepared_core)
        except CoordinatedRestoreError:
            rollback_path.unlink(missing_ok=True)
            if prepared_core is not None:
                prepared_core.cleanup()
            raise
        except Exception as exc:
            rollback_path.unlink(missing_ok=True)
            if prepared_core is not None:
                prepared_core.cleanup()
            raise CoordinatedRestoreError("restore_prepare_failed", "restore preparation failed") from exc

    def apply_restore(
        self,
        prepared: PreparedCoordinatedRestore | RestoreJournal | str | None = None,
    ) -> CoordinatedRestoreResult:
        """Apply a prepared restore, or recover the durable journal when omitted."""

        if prepared is None:
            journal = self._read_journal()
            prepared_value = self._prepared_from_journal(journal)
        elif isinstance(prepared, PreparedCoordinatedRestore):
            completed = self._completed_results.get(prepared.restore_id)
            if completed is not None:
                return completed
            prepared_value = prepared
            journal = prepared.journal
        elif isinstance(prepared, RestoreJournal):
            journal = prepared
            prepared_value = self._prepared_from_journal(journal)
        else:
            journal = self._read_journal()
            if journal.restore_id != prepared:
                raise CoordinatedRestoreError("restore_id_mismatch", "restore id does not match journal")
            prepared_value = self._prepared_from_journal(journal)

        if journal.state == "committed":
            return CoordinatedRestoreResult(journal.restore_id, "committed", journal.core_restore_transaction_id)
        if journal.state == "restore_inconsistent":
            raise CoordinatedRestoreError(
                "restore_inconsistent",
                "a previous restore is inconsistent and blocks readiness",
                restore_id=journal.restore_id,
                inconsistent=True,
            )

        stopped = False
        began = journal.core_restore_transaction_id is not None
        try:
            self.stop_core()
            stopped = True
            began = True
            journal = self._begin_if_needed(journal)
            self._replace_rounds_database(prepared_value.journal.rounds_snapshot_path)
            journal = journal.with_state("rounds_applied_pending_commit")
            self._write_journal(journal)
            stopped = False
            self.start_core()
            self._require_healthy()
            self._verify_core_manifest(journal)
            journal = journal.with_state("healthy_pending_commit")
            self._write_journal(journal)
            commit = self._commit(journal)
            journal = journal.with_state("committed")
            self._write_journal(journal)
            result = CoordinatedRestoreResult(
                journal.restore_id,
                commit.state,
                commit.restore_transaction_id,
            )
            self._completed_results[journal.restore_id] = result
            self._cleanup_success(journal)
            return result
        except CoordinatedRestoreError as exc:
            if exc.inconsistent or exc.compensated:
                raise
            if began:
                self._compensate(journal, exc.code, stopped)
            else:
                if stopped:
                    self._safe_start_after_failure()
                self._cleanup_failed_before_begin(journal)
            raise
        except Exception as exc:
            error = CoordinatedRestoreError(
                "restore_apply_failed",
                "coordinated restore failed",
                restore_id=journal.restore_id,
            )
            if began:
                self._compensate(journal, error.code, stopped)
            else:
                if stopped:
                    self._safe_start_after_failure()
                self._cleanup_failed_before_begin(journal)
            raise error from exc

    def recover(self) -> CoordinatedRestoreResult | None:
        """Recover a journal left by a crash, using Core's idempotent begin."""

        journal = self._read_journal_or_none()
        if journal is None:
            return None
        if journal.state == "restore_inconsistent":
            raise CoordinatedRestoreError(
                "restore_inconsistent",
                "a previous restore is inconsistent and blocks readiness",
                restore_id=journal.restore_id,
                inconsistent=True,
            )
        if journal.state == "committed":
            self._cleanup_success(journal)
            return CoordinatedRestoreResult(journal.restore_id, "committed", journal.core_restore_transaction_id)
        if journal.state == "prepared" and journal.core_restore_transaction_id is None:
            self._cleanup_failed_before_begin(journal)
            return CoordinatedRestoreResult(journal.restore_id, "rolled_back", None)
        try:
            self.stop_core()
            if journal.core_restore_transaction_id is None:
                journal = self._begin_if_needed(journal)
            self._rollback_core(journal)
            self._restore_rounds_database(journal.rounds_rollback_path)
            self._verify_rounds_database()
            self.start_core()
            self._require_healthy()
            journal = journal.with_state("rolled_back")
            self._write_journal(journal)
            self._cleanup_success(journal)
            return CoordinatedRestoreResult(journal.restore_id, "rolled_back", journal.core_restore_transaction_id)
        except Exception as exc:
            self._mark_inconsistent(journal)
            raise CoordinatedRestoreError(
                "restore_inconsistent",
                "restore recovery failed; manual recovery is required",
                restore_id=journal.restore_id,
                inconsistent=True,
            ) from exc

    recover_pending = recover

    def _begin_if_needed(self, journal: RestoreJournal) -> RestoreJournal:
        if journal.core_restore_transaction_id is not None:
            return journal
        pending = journal.with_state("begin_pending")
        self._write_journal(pending)
        command = BeginRestoreCommand(
            request_id=f"local-begin:{uuid.uuid4()}",
            relative_path=journal.core_relative_path,
            sha256=journal.core_sha256,
            restore_token=journal.core_restore_token,
        )
        result = self._begin(command)
        updated = journal.with_state("applied_pending_commit", transaction_id=result.restore_transaction_id)
        self._write_journal(updated)
        if result.relative_path != journal.core_relative_path or result.sha256 != journal.core_sha256:
            self._compensate(updated, "restore_manifest_mismatch", stopped=True)
        if result.size_bytes != journal.core_size_bytes or result.schema_version != journal.core_schema_version:
            self._compensate(updated, "restore_manifest_mismatch", stopped=True)
        return updated

    def _commit(self, journal: RestoreJournal) -> CommitRestoreResult:
        transaction_id = journal.core_restore_transaction_id
        if transaction_id is None:
            raise CoordinatedRestoreError("restore_commit_failed", "Core transaction is missing", restore_id=journal.restore_id)
        try:
            result = self.core_backup_service.gateway.commit_restore(
                CommitRestoreCommand(
                    request_id=f"local-commit:{uuid.uuid4()}",
                    restore_transaction_id=transaction_id,
                )
            )
            if isinstance(result, CommitRestoreResult):
                return result
            if isinstance(result, Mapping):
                return CommitRestoreResult.from_payload(result)
            return CommitRestoreResult.from_payload(result.to_payload())
        except Exception as exc:
            raise CoordinatedRestoreError("restore_commit_failed", "Core restore commit failed", restore_id=journal.restore_id) from exc

    def _rollback_core(self, journal: RestoreJournal) -> RollbackRestoreResult:
        transaction_id = journal.core_restore_transaction_id
        if transaction_id is None:
            raise CoordinatedRestoreError("restore_rollback_failed", "Core transaction is missing", restore_id=journal.restore_id)
        result = self.core_backup_service.gateway.rollback_restore(
            RollbackRestoreCommand(
                request_id=f"local-rollback:{uuid.uuid4()}",
                restore_transaction_id=transaction_id,
            )
        )
        if isinstance(result, RollbackRestoreResult):
            return result
        if isinstance(result, Mapping):
            return RollbackRestoreResult.from_payload(result)
        return RollbackRestoreResult.from_payload(result.to_payload())

    def _begin(self, command: BeginRestoreCommand) -> BeginRestoreResult:
        result = self.core_backup_service.gateway.begin_restore(command)
        if isinstance(result, BeginRestoreResult):
            return result
        if isinstance(result, Mapping):
            return BeginRestoreResult.from_payload(result)
        return BeginRestoreResult.from_payload(result.to_payload())

    def _verify_core_manifest(self, journal: RestoreJournal) -> None:
        if journal.backup_id != journal.core_sha256:
            raise CoordinatedRestoreError(
                "restore_manifest_mismatch",
                "durable restore journal changed its backup identity",
                restore_id=journal.restore_id,
            )
        if journal.core_size_bytes < 0 or journal.core_schema_version <= 0:
            raise CoordinatedRestoreError(
                "restore_manifest_mismatch",
                "durable restore journal has invalid Core metadata",
                restore_id=journal.restore_id,
            )

    def _replace_rounds_database(self, source: Path) -> None:
        if not source.is_file():
            raise CoordinatedRestoreError("restore_rounds_failed", "staged rounds database is missing")
        try:
            self._verify_sqlite(source)
            _atomic_copy(source, self.rounds_database_path)
            _remove_sqlite_sidecars(self.rounds_database_path)
            self._verify_rounds_database()
        except CoordinatedRestoreError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise CoordinatedRestoreError("restore_rounds_failed", "rounds database replacement failed") from exc

    def _restore_rounds_database(self, source: Path) -> None:
        if not source.is_file():
            raise CoordinatedRestoreError("restore_rounds_failed", "rounds rollback snapshot is missing")
        try:
            self._verify_sqlite(source)
            _atomic_copy(source, self.rounds_database_path)
            _remove_sqlite_sidecars(self.rounds_database_path)
        except CoordinatedRestoreError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise CoordinatedRestoreError("restore_rounds_failed", "rounds rollback failed") from exc

    def _verify_rounds_database(self) -> None:
        self._verify_sqlite(self.rounds_database_path)

    @staticmethod
    def _verify_sqlite(path: Path) -> None:
        try:
            connection = sqlite3.connect(path)
            try:
                result = connection.execute("PRAGMA integrity_check").fetchone()
            finally:
                connection.close()
        except (OSError, sqlite3.DatabaseError) as exc:
            raise CoordinatedRestoreError("restore_rounds_corrupt", "rounds database is corrupt") from exc
        if result is None or result[0] != "ok":
            raise CoordinatedRestoreError("restore_rounds_corrupt", "rounds database failed integrity check")

    def _compensate(self, journal: RestoreJournal, original_code: str, stopped: bool) -> None:
        if journal.core_restore_transaction_id is None:
            try:
                self._write_journal(journal.with_state("begin_pending"))
            except Exception as exc:
                self._mark_inconsistent(journal)
                raise CoordinatedRestoreError(
                    "restore_inconsistent",
                    "Core begin outcome is unknown and the journal could not be persisted",
                    restore_id=journal.restore_id,
                    inconsistent=True,
                ) from exc
            raise CoordinatedRestoreError(
                original_code,
                "Core begin outcome is pending recovery",
                restore_id=journal.restore_id,
                compensated=True,
            )
        failures: list[BaseException] = []
        if not stopped:
            try:
                self.stop_core()
            except Exception as exc:  # noqa: BLE001
                failures.append(exc)
        try:
            self._rollback_core(journal)
        except Exception as exc:  # noqa: BLE001
            failures.append(exc)
        try:
            self._restore_rounds_database(journal.rounds_rollback_path)
            self._verify_rounds_database()
        except Exception as exc:  # noqa: BLE001
            failures.append(exc)
        try:
            self.start_core()
            self._require_healthy()
        except Exception as exc:  # noqa: BLE001
            failures.append(exc)
        if failures:
            self._mark_inconsistent(journal)
            raise CoordinatedRestoreError(
                "restore_inconsistent",
                "restore compensation failed; manual recovery is required",
                restore_id=journal.restore_id,
                inconsistent=True,
            ) from failures[0]
        rolled_back = journal.with_state("rolled_back")
        self._write_journal(rolled_back)
        self._cleanup_success(rolled_back)
        raise CoordinatedRestoreError(
            original_code,
            "coordinated restore was rolled back",
            restore_id=journal.restore_id,
            compensated=True,
        )

    def _require_healthy(self) -> None:
        value = self.health_check()
        healthy = value is True or (
            isinstance(value, Mapping) and value.get("healthy") is True
        ) or getattr(value, "healthy", False) is True
        if not healthy:
            raise CoordinatedRestoreError("restore_health_failed", "Core health check failed")

    def _safe_start_after_failure(self) -> None:
        try:
            self.start_core()
        except Exception as exc:  # noqa: BLE001
            del exc

    def _cleanup_failed_before_begin(self, journal: RestoreJournal) -> None:
        journal.rounds_rollback_path.unlink(missing_ok=True)
        journal.core_exchange_path.unlink(missing_ok=True)
        shutil.rmtree(journal.staging_dir, ignore_errors=True)
        self.journal_path.unlink(missing_ok=True)

    def _cleanup_success(self, journal: RestoreJournal) -> None:
        journal.rounds_rollback_path.unlink(missing_ok=True)
        journal.core_exchange_path.unlink(missing_ok=True)
        shutil.rmtree(journal.staging_dir, ignore_errors=True)
        self.journal_path.unlink(missing_ok=True)
        _sync_directory(self.journal_path.parent)

    def _mark_inconsistent(self, journal: RestoreJournal) -> None:
        try:
            self._write_journal(journal.with_state("restore_inconsistent"))
        except Exception as exc:  # noqa: BLE001
            del exc

    def _prepared_from_journal(self, journal: RestoreJournal) -> PreparedCoordinatedRestore:
        preparation = PrepareRestoreResult(
            relative_path=journal.core_relative_path,
            sha256=journal.core_sha256,
            size_bytes=journal.core_size_bytes,
            schema_version=journal.core_schema_version,
            restore_token=journal.core_restore_token,
            requires_restart=True,
        )
        prepared_core = PreparedCoreRestore(
            archive_path=Path("<journal-recovery>"),
            staging_dir=journal.staging_dir,
            rounds_snapshot_path=journal.rounds_snapshot_path,
            core_exchange_path=journal.core_exchange_path,
            preparation=preparation,
        )
        return PreparedCoordinatedRestore(journal=journal, prepared_core=prepared_core)

    def _read_journal_or_none(self) -> RestoreJournal | None:
        if not self.journal_path.exists():
            return None
        return self._read_journal()

    def _read_journal(self) -> RestoreJournal:
        try:
            with self.journal_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            if not isinstance(payload, Mapping):
                raise TypeError("journal must be an object")
            journal = RestoreJournal.from_payload(payload)
            self._validate_journal_paths(journal)
            return journal
        except CoordinatedRestoreError:
            raise
        except Exception as exc:
            raise CoordinatedRestoreError("restore_journal_corrupt", "restore journal is corrupt") from exc

    def _validate_journal_paths(self, journal: RestoreJournal) -> None:
        core_root = self.core_backup_service.core_data_dir.resolve()
        rollback_root = self._rollback_root.resolve()

        def within(path: Path, root: Path) -> bool:
            try:
                path.resolve().relative_to(root)
            except ValueError:
                return False
            return True

        if not within(journal.rounds_rollback_path, rollback_root):
            raise CoordinatedRestoreError("restore_journal_corrupt", "rollback path escapes the private rollback directory")
        if not within(journal.staging_dir, core_root) or not within(journal.rounds_snapshot_path, core_root):
            raise CoordinatedRestoreError("restore_journal_corrupt", "staging path escapes Core's private staging directory")
        if not within(journal.core_exchange_path, core_root / "exchange" / "incoming"):
            raise CoordinatedRestoreError("restore_journal_corrupt", "Core exchange path escapes incoming")
        expected_exchange = core_root.joinpath(*Path(journal.core_relative_path).parts)
        if expected_exchange.resolve() != journal.core_exchange_path.resolve():
            raise CoordinatedRestoreError("restore_journal_corrupt", "Core exchange path does not match its relative path")
        if not journal.core_sha256.startswith("sha256:") or len(journal.core_sha256) != 71:
            raise CoordinatedRestoreError("restore_journal_corrupt", "Core digest is malformed")

    def _write_journal(self, journal: RestoreJournal) -> None:
        temporary = self.journal_path.with_name(f".{self.journal_path.name}.{uuid.uuid4().hex}.tmp")
        payload = json.dumps(journal.to_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.journal_path)
            os.chmod(self.journal_path, 0o600)
            _sync_directory(self.journal_path.parent)
        finally:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class CoordinatedRestoreResult:
    restore_id: str
    state: str
    core_restore_transaction_id: str | None


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoordinatedRestoreError("restore_journal_corrupt", f"{name} is missing")
    return value


def _safe_identifier(value: object, name: str) -> str:
    text = _required_text(value, name)
    if len(text) > 256 or any(character in text for character in ("/", "\\", "\x00")):
        raise CoordinatedRestoreError("restore_journal_corrupt", f"{name} is unsafe")
    return text


def _safe_exchange_path(value: object) -> str:
    text = _required_text(value, "core_relative_path")
    parts = Path(text).parts
    if "\\" in text or text.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise CoordinatedRestoreError("restore_journal_corrupt", "Core exchange path is unsafe")
    if parts[:2] != ("exchange", "incoming") or len(parts) < 3:
        raise CoordinatedRestoreError("restore_journal_corrupt", "Core exchange path is outside incoming")
    return text


def _journal_path(value: object, name: str) -> Path:
    text = _required_text(value, name)
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise CoordinatedRestoreError("restore_journal_corrupt", f"{name} must be absolute")
    return path


def _remove_sqlite_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def _sync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


CoordinatedRestore = CoordinatedRestoreService
LocalRestoreSaga = CoordinatedRestoreService


__all__ = [
    "CoordinatedRestore",
    "CoordinatedRestoreError",
    "CoordinatedRestoreResult",
    "CoordinatedRestoreService",
    "LocalRestoreSaga",
    "PreparedCoordinatedRestore",
    "RestoreJournal",
]
