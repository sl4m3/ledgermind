"""Signed release updates (online layered or full, offline) and atomic rollback."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from ...inference.profile_slots import ProfileSlot
from ...inference.profile_store import InferenceProfileStore
from ...inference.profiles import generation_profile_fingerprint
from ...persistence import open_sqlite_connection
from ...runtime.supervisor import RuntimeSupervisor
from ..config_writer import load_installer_config, write_local_config
from ..errors import ConfigurationError
from ..lock import InstallerLock
from ..models import InstallerConfig
from ..paths import InstallerPaths
from ..preflight import platform_id
from ..transaction import FileBackup, _atomic_symlink
from ..verify import public_key_from_environment, verify_bundle_tree
from .common import (
    assemble_layered_bundle,
    compute_runtime_layer_digest,
    fetch_bundle,
    fetch_manifest,
    format_transfer_progress,
    install_bin_link,
    installed_release_version,
    layered_patch_record,
    prune_old_releases,
    write_install_history,
    write_update_check_cache,
)
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
            ProfileSlot.RESOLUTION_DECISION,
        ):
            rows = connection.execute(
                "SELECT DISTINCT profile_id FROM memory_space_model_profiles "
                "WHERE profile_slot = ? ORDER BY profile_id",
                (slot.value,),
            ).fetchall()
            if not rows:
                if slot == ProfileSlot.RESOLUTION_DECISION:
                    continue
                missing.append(f"{slot.value}:unbound")
                continue
            for row in rows:
                profile_id = str(row[0])
                profile = store.get(profile_id)
                if profile is None:
                    missing.append(f"{slot.value}:{profile_id}:missing_profile")
                    continue
                if slot == ProfileSlot.RESOLUTION_DECISION:
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


@contextmanager
def _update_barrier(paths: InstallerPaths):
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
        yield
    finally:
        barrier.unlink(missing_ok=True)


def _backup_files(*targets: Path) -> list[FileBackup]:
    backups: list[FileBackup] = []
    for path in targets:
        if path.is_file():
            backups.append(
                FileBackup(
                    path,
                    True,
                    path.read_bytes(),
                    path.stat().st_mode & 0o777,
                )
            )
        else:
            backups.append(FileBackup(path, False))
    return backups


def _restore_files(backups: list[FileBackup]) -> None:
    for item in backups:
        if item.existed:
            item.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            item.path.write_bytes(item.content)
            os.chmod(item.path, item.mode)
        else:
            item.path.unlink(missing_ok=True)


def check_update(
    *,
    paths: InstallerPaths,
    version: str | None = None,
    public_key: bytes | str | None = None,
) -> dict[str, Any]:
    """Check for a signed LedgerMind release without modifying the installation."""

    paths.ensure()
    key = public_key or public_key_from_environment()
    _manifest_path, _signature_path, manifest = fetch_manifest(
        paths, public_key=key, version=version
    )
    installed_version = installed_release_version(paths)
    plat = platform_id()
    full_record = manifest.platform(plat).bundle
    patch_available = False
    download_bytes = full_record.size
    patch_info = layered_patch_record(manifest, platform=plat)
    if patch_info is not None and paths.current_link.exists():
        patch_artifact, expected_base_sha = patch_info
        current_release = paths.current_link.resolve()
        actual_base_sha = compute_runtime_layer_digest(
            current_release / "bundle-manifest.json"
        )
        if (
            actual_base_sha == expected_base_sha
            and (current_release / "embedding-runtimes").is_dir()
            and (current_release / "python" / "runtime").is_dir()
        ):
            patch_available = True
            download_bytes = patch_artifact.size
    payload = {
        "status": "passed",
        "installed_version": installed_version,
        "latest_version": manifest.release_version,
        "release_version": manifest.release_version,
        "published_at": manifest.published_at,
        "update_available": installed_version != manifest.release_version,
        "layered_patch_available": patch_available,
        "download_bytes": download_bytes,
        "full_bundle_bytes": full_record.size,
    }
    write_update_check_cache(paths, payload)
    return payload


def _update_transaction(
    *,
    config: InstallerConfig,
    paths: InstallerPaths,
    manifest_path: str | Path | None = None,
    bundle: str | Path | None = None,
    manifest_signature: str | Path | None = None,
    version: str | None = None,
    force: bool = False,
    keep_releases: int = 2,
    public_key: bytes | str | None = None,
    dry_run: bool = False,
    skip_provider_probe: bool = False,
    generation_stdin: str | None = None,
    embedding_stdin: str | None = None,
    progress: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    if (manifest_path is None) != (bundle is None):
        raise ConfigurationError("--manifest and --bundle must be provided together")
    if dry_run:
        return {
            "status": "dry_run",
            "operation": "update",
            "source": "offline" if manifest_path is not None else "online",
            "version": version,
        }

    report = progress or (lambda _phase, _message: None)
    key = public_key or public_key_from_environment()
    previous_version = installed_release_version(paths)
    previous_target = (
        os.readlink(paths.current_link) if paths.current_link.is_symlink() else None
    )
    previous_release_path = (
        paths.current_link.resolve() if paths.current_link.exists() else None
    )
    delivery_mode = "offline-bundle"
    assembled_dir: Path | None = None

    try:
        if manifest_path is None and bundle is None:
            report("download", "Checking for available release updates")
            fetched_manifest, fetched_signature, manifest = fetch_manifest(
                paths, public_key=key, version=version
            )
            manifest_path = fetched_manifest
            manifest_signature = fetched_signature
            if previous_version == manifest.release_version and not force:
                write_update_check_cache(
                    paths,
                    {
                        "installed_version": previous_version,
                        "latest_version": manifest.release_version,
                        "release_version": manifest.release_version,
                        "update_available": False,
                    },
                )
                return {
                    "status": "passed",
                    "up_to_date": True,
                    "installed_version": previous_version,
                    "release_version": manifest.release_version,
                    "delivery_mode": "up-to-date",
                }
            if previous_release_path is not None:
                report("download", "Checking fast layered update availability")
                assembled_dir = assemble_layered_bundle(
                    paths=paths,
                    manifest=manifest,
                    current_release=previous_release_path,
                    public_key=key,
                    version=version,
                    progress=lambda transferred, total: report(
                        "download",
                        format_transfer_progress("Update patch", transferred, total),
                    ),
                )
            if assembled_dir is not None:
                bundle = assembled_dir
                delivery_mode = "layered-patch"
            else:
                bundle = fetch_bundle(
                    paths,
                    manifest,
                    public_key=key,
                    version=version,
                    progress=lambda transferred, total: report(
                        "download",
                        format_transfer_progress("Release bundle", transferred, total),
                    ),
                )
                delivery_mode = "full-bundle"

        RuntimeSupervisor(paths).stop(force=True)
        backups = _backup_files(
            paths.config_file,
            paths.profiles_file,
            paths.secrets_file,
            paths.config_dir / "local-config.json",
            paths.data_dir / "local" / "config.json",
            paths.data_dir / "embedding" / "server.token",
        )
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
            result: dict[str, Any] = {}
            try:
                install_kwargs: dict[str, Any] = {
                    "config": config,
                    "paths": paths,
                    "manifest_path": manifest_path,
                    "bundle": bundle,
                    "skip_provider_probe": skip_provider_probe,
                    "generation_stdin": generation_stdin,
                    "embedding_stdin": embedding_stdin,
                    "preserve_provider_credentials": True,
                }
                if manifest_signature is not None:
                    install_kwargs["manifest_signature"] = manifest_signature
                if public_key is not None:
                    install_kwargs["public_key"] = public_key
                if force:
                    install_kwargs["replace_existing"] = True
                if progress is not None:
                    install_kwargs["progress"] = progress
                result = install(**install_kwargs)
                if skip_provider_probe:
                    _assert_generation_capabilities_ready(database)
                # Provider preflight already ran inside install unless the caller
                # explicitly skipped it. Do not duplicate billable network calls,
                # and honor the skip flag during the post-update local diagnostic.
                result["doctor"] = doctor(paths=paths, probe_providers=False)
                if result["doctor"].get("status") != "passed":
                    raise RuntimeError("doctor failed after update")
                protect_paths = (
                    (previous_release_path,)
                    if (previous_release_path is not None and keep_releases >= 2)
                    else ()
                )
                pruned = prune_old_releases(
                    paths, keep=keep_releases, protect=protect_paths
                )
                new_version = str(result.get("release_version") or "")
                write_update_check_cache(
                    paths,
                    {
                        "installed_version": new_version,
                        "latest_version": new_version,
                        "release_version": new_version,
                        "update_available": False,
                    },
                )
                write_install_history(
                    paths,
                    {
                        "operation": "update",
                        "previous_version": previous_version,
                        "release_version": new_version,
                        "delivery_mode": delivery_mode,
                        "timestamp": time.time(),
                        "current": str(paths.current_link),
                    },
                )
                result["previous_version"] = previous_version
                result["delivery_mode"] = delivery_mode
                result["pruned_releases"] = pruned
                result["rollback_available"] = bool(
                    previous_release_path is not None
                    and previous_release_path.is_dir()
                    and previous_version != new_version
                )
                return result
            except Exception as exc:
                if previous_target is not None:
                    _atomic_symlink(Path(previous_target), paths.current_link)
                _restore_files(backups)
                for path, (existed, backup) in database_backups.items():
                    if existed and backup is not None:
                        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        shutil.copy2(backup, path)
                    else:
                        path.unlink(missing_ok=True)
                # Keep the previous release and remove only the newly committed one.
                if previous_target is not None:
                    new_release = (
                        paths.releases_dir / str(result.get("release_version", ""))
                        if result
                        else None
                    )
                    if (
                        new_release is not None
                        and str(result.get("release_version", ""))
                        and new_release != Path(previous_target)
                    ):
                        shutil.rmtree(new_release, ignore_errors=True)
                raise RuntimeError(
                    f"update failed and previous release was retained: {exc}"
                ) from exc
    finally:
        if assembled_dir is not None:
            shutil.rmtree(paths.staging_dir / "bundle-layered", ignore_errors=True)


def update(
    *,
    config: InstallerConfig,
    paths: InstallerPaths,
    manifest_path: str | Path | None = None,
    bundle: str | Path | None = None,
    manifest_signature: str | Path | None = None,
    version: str | None = None,
    force: bool = False,
    keep_releases: int = 2,
    public_key: bytes | str | None = None,
    dry_run: bool = False,
    skip_provider_probe: bool = False,
    generation_stdin: str | None = None,
    embedding_stdin: str | None = None,
    progress: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Run one update while preventing hooks from restarting the old runtime."""

    if (manifest_path is None) != (bundle is None):
        raise ConfigurationError("--manifest and --bundle must be provided together")
    if dry_run:
        return {
            "status": "dry_run",
            "operation": "update",
            "source": "offline" if manifest_path is not None else "online",
            "version": version,
        }
    with _update_barrier(paths):
        return _update_transaction(
            config=config,
            paths=paths,
            manifest_path=manifest_path,
            bundle=bundle,
            manifest_signature=manifest_signature,
            version=version,
            force=force,
            keep_releases=keep_releases,
            public_key=public_key,
            dry_run=False,
            skip_provider_probe=skip_provider_probe,
            generation_stdin=generation_stdin,
            embedding_stdin=embedding_stdin,
            progress=progress,
        )


def _select_rollback_candidate(
    paths: InstallerPaths, *, current_dir: Path, target_version: str | None
) -> Path:
    if target_version is not None and target_version.strip():
        candidate = paths.release_dir(target_version.strip())
        if not candidate.is_dir():
            raise ConfigurationError(
                f"requested rollback release does not exist: {target_version}"
            )
        if candidate.resolve() == current_dir:
            raise ConfigurationError(
                f"release {target_version} is already the active version"
            )
        if not (candidate / "bundle-manifest.json").is_file():
            raise ConfigurationError(
                f"release {target_version} has no bundle manifest"
            )
        return candidate.resolve()

    candidates: list[tuple[float, Path]] = []
    if paths.releases_dir.is_dir():
        for entry in paths.releases_dir.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            try:
                resolved = entry.resolve()
            except OSError:
                continue
            if resolved == current_dir:
                continue
            if not (resolved / "bundle-manifest.json").is_file():
                continue
            candidates.append((entry.stat().st_mtime, resolved))
    if not candidates:
        raise ConfigurationError("no previous release is available to roll back to")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def rollback(
    *,
    paths: InstallerPaths,
    target_version: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Switch back cleanly to a verified previous release under ``releases/``."""

    if not paths.config_file.is_file() or not paths.current_link.exists():
        raise ConfigurationError("LedgerMind must be installed before rollback")
    config = load_installer_config(paths.config_file)
    current_dir = paths.current_link.resolve()
    previous_version = installed_release_version(paths) or current_dir.name
    candidate = _select_rollback_candidate(
        paths, current_dir=current_dir, target_version=target_version
    )
    verify_bundle_tree(candidate)
    try:
        manifest_payload = json.loads(
            (candidate / "bundle-manifest.json").read_text(encoding="utf-8")
        )
        candidate_version = str(manifest_payload.get("release_version") or candidate.name)
    except (OSError, ValueError):
        candidate_version = candidate.name

    if dry_run:
        return {
            "status": "dry_run",
            "operation": "rollback",
            "previous_version": previous_version,
            "release_version": candidate_version,
            "release_dir": str(candidate),
        }

    with _update_barrier(paths), InstallerLock(paths.install_lock):
        backups = _backup_files(
            paths.profiles_file,
            paths.config_dir / "local-config.json",
            paths.data_dir / "local" / "config.json",
        )
        previous_target = (
            os.readlink(paths.current_link)
            if paths.current_link.is_symlink()
            else str(current_dir)
        )
        RuntimeSupervisor(paths).stop(force=True)
        try:
            _atomic_symlink(candidate, paths.current_link)
            install_bin_link(paths)
            write_local_config(config, paths, release_dir=candidate)
            doctor_report = doctor(
                paths=paths,
                full_smoke=True,
                probe_providers=False,
                verify_integrations=False,
            )
            if doctor_report.get("status") != "passed":
                raise RuntimeError("doctor verification failed after rollback")
        except Exception as exc:
            _atomic_symlink(Path(previous_target), paths.current_link)
            _restore_files(backups)
            with suppress(Exception):
                install_bin_link(paths)
            raise RuntimeError(
                f"rollback failed and active release was restored: {exc}"
            ) from exc

        write_update_check_cache(
            paths,
            {
                "installed_version": candidate_version,
                "latest_version": previous_version,
                "release_version": previous_version,
                "update_available": candidate_version != previous_version,
            },
        )
        write_install_history(
            paths,
            {
                "operation": "rollback",
                "previous_version": previous_version,
                "release_version": candidate_version,
                "timestamp": time.time(),
                "current": str(paths.current_link),
            },
        )
        return {
            "status": "passed",
            "previous_version": previous_version,
            "release_version": candidate_version,
            "current": str(paths.current_link),
            "release_dir": str(candidate),
            "doctor": doctor_report,
        }


__all__ = ["check_update", "rollback", "update"]
