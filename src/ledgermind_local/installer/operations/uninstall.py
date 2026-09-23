"""Safe uninstall preserving user memory/config by default."""

from __future__ import annotations

import os
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...runtime.supervisor import RuntimeSupervisor
from ..config_writer import select_secret_backend
from ..paths import InstallerPaths
from ..secret_refs import (
    EMBEDDING_SECRET_REF,
    GENERATION_SECRET_REF,
    LEGACY_EMBEDDING_SECRET_REF,
    LEGACY_GENERATION_SECRET_REF,
)
from ..targets.base import AdapterContext
from ..targets.registry import get_target_adapter
from .common import remove_bin_link


def _backup_preserved_memory(
    *, paths: InstallerPaths, config: Any | None
) -> Path | None:
    source = paths.memory_data_dir
    if config is not None and config.memory_data_path:
        source = Path(config.memory_data_path).expanduser()
    if not source.is_dir():
        return None
    backup_dir = paths.state_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(backup_dir, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = backup_dir / f"ledgermind-memory-uninstall-{stamp}.tar.gz"
    suffix = 1
    while archive.exists():
        archive = backup_dir / f"ledgermind-memory-uninstall-{stamp}-{suffix}.tar.gz"
        suffix += 1
    with tarfile.open(archive, "x:gz") as handle:
        handle.add(source, arcname="memory-data", recursive=True)
    os.chmod(archive, 0o600)
    return archive


def uninstall(
    *,
    paths: InstallerPaths,
    purge_data: bool = False,
    purge_config: bool = False,
    yes: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    if (purge_data or purge_config) and not yes:
        raise ValueError("--yes is required with purge flags")
    if dry_run:
        return {
            "status": "dry_run",
            "purge_data": purge_data,
            "purge_config": purge_config,
            "preserved_data": not purge_data,
            "preserved_config": not purge_config,
        }
    config = None
    if paths.config_file.is_file():
        from ..config_writer import load_installer_config

        config = load_installer_config(paths.config_file)
    RuntimeSupervisor(paths).stop(force=True)
    backup_path = (
        None if purge_data else _backup_preserved_memory(paths=paths, config=config)
    )
    adapter_result: dict[str, Any] = {}
    if config is not None:
        for selected in config.integrations:
            adapter = get_target_adapter(selected.id)
            discovery = adapter.discover()
            if discovery.detected:
                adapter_result[selected.id] = adapter.uninstall(
                    AdapterContext(config=config, paths=paths, discovery=discovery),
                    purge=False,
                )
    remove_bin_link(paths)
    if paths.current_link.is_symlink():
        paths.current_link.unlink(missing_ok=True)
    releases_removed = 0
    if paths.releases_dir.exists():
        for release in paths.releases_dir.iterdir():
            if release.is_dir():
                shutil.rmtree(release)
                releases_removed += 1
    if purge_data:
        shutil.rmtree(paths.memory_data_dir, ignore_errors=True)
        shutil.rmtree(paths.models_dir, ignore_errors=True)
        shutil.rmtree(paths.integrations_dir, ignore_errors=True)
        if config is not None and config.memory_data_path:
            custom_memory = Path(config.memory_data_path).expanduser()
            if custom_memory != paths.memory_data_dir:
                shutil.rmtree(custom_memory, ignore_errors=True)
    if purge_config:
        backend = select_secret_backend(paths)
        for secret_ref in (
            GENERATION_SECRET_REF,
            EMBEDDING_SECRET_REF,
            LEGACY_GENERATION_SECRET_REF,
            LEGACY_EMBEDDING_SECRET_REF,
        ):
            backend.delete(secret_ref)
        shutil.rmtree(paths.config_dir, ignore_errors=True)
        shutil.rmtree(paths.data_dir / "local", ignore_errors=True)
    return {
        "status": "passed",
        "integrations": adapter_result,
        "releases_removed": releases_removed,
        "preserved_data": not purge_data,
        "preserved_config": not purge_config,
        "memory_backup": str(backup_path) if backup_path is not None else None,
        "backup_status": (
            "skipped_purge"
            if purge_data
            else ("created" if backup_path is not None else "no_memory_data")
        ),
    }
