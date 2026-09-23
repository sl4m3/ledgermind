"""Closed technical profile slots and their resolution to configured profiles."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from .profile_store import InferenceProfileStore
from .profiles import InferenceProfile


class ProfileSlot(str, Enum):
    """Closed set of technical slots selecting a configured inference profile.

    A slot is a selection of a configured profile, not a domain facet.
    """

    OPERATIONAL = "operational"
    OBJECT_RESOLUTION = "object_resolution"
    BACKGROUND = "background"
    EMBEDDING = "embedding"

    def __str__(self) -> str:
        return self.value


class MissingProfileError(RuntimeError):
    """Structured failure raised when a slot has no resolvable profile."""

    code = "profile_missing"

    def __init__(
        self,
        *,
        slot: ProfileSlot,
        memory_space_id: str,
        profile_id: str | None = None,
        reason: str = "profile_not_found",
    ) -> None:
        self.slot = slot
        self.memory_space_id = memory_space_id
        self.profile_id = profile_id
        self.reason = reason
        super().__init__(
            f"no {slot.value} profile for memory space {memory_space_id!r}"
            + (f" (profile {profile_id!r} {reason})" if profile_id else f" ({reason})")
        )


class ProfileResolver:
    """Service interface selecting a configured profile for a technical slot."""

    def resolve_profile(
        self, memory_space_id: str, slot: ProfileSlot
    ) -> InferenceProfile:
        """Return the configured profile for ``slot`` or raise MissingProfileError."""
        raise NotImplementedError


class StoreBackedProfileResolver(ProfileResolver):
    """Base resolution over the existing inference profile store.

    Extension point for C2: real storage/settings wiring can subclass this
    resolver (or implement ProfileResolver directly) without touching A3 code.
    """

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
