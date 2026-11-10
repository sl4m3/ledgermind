"""Closed technical profile slots and their resolution to configured profiles."""

from __future__ import annotations

from pathlib import Path

from ledgermind_inference.profile_slots import (
    MissingProfileError,
    ProfileResolver,
    ProfileSlot,
)
from .profile_store import InferenceProfileStore
from .profiles import InferenceProfile


class StoreBackedProfileResolver(ProfileResolver):
    """Base resolution over the existing inference profile store."""

    def __init__(
        self, profile_store: InferenceProfileStore
    ) -> None:
        self._profile_store = profile_store

    @property
    def profile_store(self) -> InferenceProfileStore:
        """Expose the same Local-owned store for capability lookups."""
        return self._profile_store

    def resolve_profile(
        self, memory_space_id: str, slot: ProfileSlot
    ) -> InferenceProfile:
        profile_id = self._profile_store.get_slot(memory_space_id, slot.value)
        if profile_id is None:
            raise MissingProfileError(
                slot=slot,
                memory_space_id=memory_space_id,
                reason="binding_missing",
            )
        profile = self._profile_store.get(profile_id)
        if profile is None:
            raise MissingProfileError(
                slot=slot,
                memory_space_id=memory_space_id,
                profile_id=profile_id,
                reason="profile_not_found",
            )
        if not profile.enabled:
            raise MissingProfileError(
                slot=slot,
                memory_space_id=memory_space_id,
                profile_id=profile_id,
                reason="profile_disabled",
            )
        return profile


class DatabaseBackedProfileResolver(ProfileResolver):
    """Resolve a slot using a fresh Local SQLite connection per lookup."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    @property
    def database_path(self) -> str | Path:
        return self._database_path

    def resolve_profile(
        self, memory_space_id: str, slot: ProfileSlot
    ) -> InferenceProfile:
        from ..persistence import open_sqlite_connection
        from ..persistence import rounds_migrations as migrations

        connection = open_sqlite_connection(self._database_path)
        try:
            migrations.apply_migrations(connection)
            resolver = StoreBackedProfileResolver(InferenceProfileStore(connection))
            return resolver.resolve_profile(memory_space_id, slot)
        finally:
            connection.close()


__all__ = [
    "DatabaseBackedProfileResolver",
    "MissingProfileError",
    "ProfileResolver",
    "ProfileSlot",
    "StoreBackedProfileResolver",
]
