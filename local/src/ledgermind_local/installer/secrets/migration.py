"""Migration from the old Local file secret store to installer storage."""

from __future__ import annotations

from pathlib import Path

from .base import SecretBackend
from .file_store import FileSecretStore


def migrate_file_secrets(
    source: str | Path,
    target: SecretBackend,
    *,
    delete_source: bool = False,
) -> tuple[str, ...]:
    source_store = FileSecretStore(source)
    migrated: list[str] = []
    for key in source_store.list_keys():
        value = source_store.get(key)
        if value is None:
            continue
        target.put(key, value)
        migrated.append(key)
    if delete_source and migrated:
        Path(source).unlink(missing_ok=True)
    return tuple(migrated)


__all__ = ["migrate_file_secrets"]
