"""Signed release update with migrations/doctor rollback boundary."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ...inference.profile_slots import ProfileSlot
from ...inference.profile_store import InferenceProfileStore
from ...inference.profiles import generation_profile_fingerprint
from ...persistence import open_sqlite_connection
from ...runtime.supervisor import RuntimeSupervisor
from ..models import InstallerConfig
from ..paths import InstallerPaths
from .doctor import doctor
from .install import install


def _assert_generation_capabilities_ready(database: Path) -> None:
    """Reject an update that leaves strict generation locally disabled.

    ``--skip-provider-probe`` is safe only when the installed release preserves
    fresh capability observations for the exact materialized profiles.  A
    release may change a fingerprinted transport field (for example an output
    budget); silently accepting the update would make every semantic task fail
    locally before an HTTP request is attempted.
    """

    if not database.is_file():
        raise RuntimeError("generation profile database is missing after update")
    connection = open_sqlite_connection(database)
    try:
        store = InferenceProfileStore(connection)
        missing: list[str] = []
        for slot in (
            ProfileSlot.OPERATIONAL,
            ProfileSlot.OBJECT_RESOLUTION,
            ProfileSlot.BACKGROUND,
        ):
            rows = connection.execute(
                "SELECT DISTINCT profile_id FROM memory_space_model_profiles "
                "WHERE profile_slot = ? ORDER BY profile_id",
                (slot.value,),
            ).fetchall()
            if not rows:
                missing.append(f"{slot.value}:unbound")
                continue
            for row in rows:
                profile_id = str(row[0])
                profile = store.get(profile_id)
                if profile is None:
                    missing.append(f"{slot.value}:{profile_id}:missing_profile")
                    continue
                capabilities = store.get_capabilities(
                    profile_id,
                    profile_fingerprint=generation_profile_fingerprint(profile),
                    fresh_only=True,
                )
                if capabilities is None or not capabilities.supports(
                    "strict_json_schema"
                ):
                    missing.append(f"{slot.value}:{profile_id}:unverified")
        if missing:
            raise RuntimeError(
                "provider probe is required because the update changed or "
                "invalidated generation capabilities: " + ", ".join(missing)
            )
    finally:
        connection.close()


def _update_transaction(
    *,
    config: InstallerConfig,
    paths: InstallerPaths,
    manifest_path: str | Path,
    bundle: str | Path,
    dry_run: bool = False,
    skip_provider_probe: bool = False,
    generation_stdin: str | None = None,
    embedding_stdin: str | None = None,
) -> dict[str, Any]:
    if dry_run:
        return {"status": "dry_run", "operation": "update"}
    RuntimeSupervisor(paths).stop(force=True)
    previous_target = (
        os.readlink(paths.current_link) if paths.current_link.is_symlink() else None
    )
    backups: dict[Path, tuple[bool, bytes, int]] = {}
    for path in (
        paths.config_file,
        paths.profiles_file,
        paths.secrets_file,
        paths.config_dir / "local-config.json",
        paths.data_dir / "local" / "config.json",
        paths.data_dir / "embedding" / "server.token",
    ):
        if path.is_file():
            backups[path] = (True, path.read_bytes(), path.stat().st_mode & 0o777)
        else:
            backups[path] = (False, b"", 0o600)
    # Installation materializes profiles in Local's SQLite database. Preserve
    # that file separately so a failed post-install diagnostic cannot leave a
    # partially upgraded database behind after the release link rolls back.
    database = paths.memory_data_dir / "rounds.db"
    database_files = (
        database,
        database.with_name("rounds.db-wal"),
        database.with_name("rounds.db-shm"),
    )
    paths.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(
        prefix=".update-rollback-", dir=paths.state_dir
    ) as temporary_name:
        rollback_dir = Path(temporary_name)
        database_backups: dict[Path, tuple[bool, Path | None]] = {}
        for index, path in enumerate(database_files):
            if path.is_file():
                destination = rollback_dir / f"database-{index}"
                shutil.copy2(path, destination)
                database_backups[path] = (True, destination)
            else:
                database_backups[path] = (False, None)
        try:
            result = install(
                config=config,
                paths=paths,
                manifest_path=manifest_path,
                bundle=bundle,
                skip_provider_probe=skip_provider_probe,
                generation_stdin=generation_stdin,
                embedding_stdin=embedding_stdin,
                preserve_provider_credentials=True,
            )
            if skip_provider_probe:
                _assert_generation_capabilities_ready(database)
            # Provider preflight already ran inside install unless the caller
            # explicitly skipped it. Do not duplicate billable network calls,
            # and honor the skip flag during the post-update local diagnostic.
            result["doctor"] = doctor(paths=paths, probe_providers=False)
            if result["doctor"].get("status") != "passed":
                raise RuntimeError("doctor failed after update")
            return result
        except Exception as exc:
            if previous_target is not None:
                temporary = paths.current_link.with_name(".current.rollback.tmp")
                temporary.unlink(missing_ok=True)
                temporary.symlink_to(previous_target)
                temporary.replace(paths.current_link)
            for path, (existed, content, mode) in backups.items():
                if existed:
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    path.write_bytes(content)
                    os.chmod(path, mode)
                else:
                    path.unlink(missing_ok=True)
            for path, (existed, backup) in database_backups.items():
                if existed and backup is not None:
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    shutil.copy2(backup, path)
                else:
                    path.unlink(missing_ok=True)
            # Keep the previous release and remove only the newly committed one.
            current = (
                paths.current_link.resolve() if paths.current_link.exists() else None
            )
            if current is not None and previous_target is not None:
                new_release = (
                    paths.releases_dir / str(result.get("release_version", ""))
                    if "result" in locals()
                    else None
                )
                if new_release is not None and new_release != Path(previous_target):
                    shutil.rmtree(new_release, ignore_errors=True)
            raise RuntimeError(
                f"update failed and previous release was retained: {exc}"
            ) from exc


def update(
    *,
    config: InstallerConfig,
    paths: InstallerPaths,
    manifest_path: str | Path,
    bundle: str | Path,
    dry_run: bool = False,
    skip_provider_probe: bool = False,
    generation_stdin: str | None = None,
    embedding_stdin: str | None = None,
) -> dict[str, Any]:
    """Run one update while preventing hooks from restarting the old runtime."""

    if dry_run:
        return {"status": "dry_run", "operation": "update"}
    paths.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    barrier = paths.runtime_dir / "update-in-progress"
    try:
        descriptor = os.open(barrier, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("another runtime update is already in progress") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
            os.fsync(handle.fileno())
        return _update_transaction(
            config=config,
            paths=paths,
            manifest_path=manifest_path,
            bundle=bundle,
            dry_run=False,
            skip_provider_probe=skip_provider_probe,
            generation_stdin=generation_stdin,
            embedding_stdin=embedding_stdin,
        )
    finally:
        barrier.unlink(missing_ok=True)


__all__ = ["update"]
