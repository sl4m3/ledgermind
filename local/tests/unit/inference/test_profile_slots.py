from __future__ import annotations

import sqlite3

import pytest

from ledgermind_local.inference.profile_slots import (
    MissingProfileError,
    ProfileSlot,
    StoreBackedProfileResolver,
)
from ledgermind_local.inference.profile_store import InferenceProfileStore
from ledgermind_local.inference.profiles import InferenceProfile
from ledgermind_local.persistence import rounds_migrations as migrations


def _setup() -> tuple[InferenceProfileStore, sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    migrations.apply_migrations(connection)
    connection.execute(
        "INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("space", "tests", "2026-08-03T00:00:00Z", "2026-08-03T00:00:00Z"),
    )
    store = InferenceProfileStore(connection)
    store.upsert(
        InferenceProfile(
            profile_id="operational-default",
            base_url="https://provider.example/v1",
            model="op-model",
            secret_ref="op-secret",
        )
    )
    store.upsert(
        InferenceProfile(
            profile_id="background-default",
            base_url="https://provider.example/v1",
            model="bg-model",
            secret_ref="bg-secret",
        )
    )
    store.upsert(
        InferenceProfile(
            profile_id="object-resolution-default",
            base_url="https://provider.example/v1",
            model="object-resolution-model",
            secret_ref="object-resolution-secret",
        )
    )
    store.upsert(
        InferenceProfile(
            profile_id="embedding-default",
            base_url="https://provider.example/v1",
            model="embed-model",
            secret_ref="embed-secret",
        )
    )
    store.bind_slot("space", slot="operational", profile_id="operational-default")
    store.bind_slot("space", slot="background", profile_id="background-default")
    store.bind_slot(
        "space", slot="object_resolution", profile_id="object-resolution-default"
    )
    store.bind_slot("space", slot="embedding", profile_id="embedding-default")
    connection.commit()
    return store, connection


def test_resolve_operational_slot_uses_operational_profile_binding() -> None:
    store, _ = _setup()
    resolver = StoreBackedProfileResolver(store)

    profile = resolver.resolve_profile("space", ProfileSlot.OPERATIONAL)

    assert profile.profile_id == "operational-default"
    assert profile.model == "op-model"


def test_resolve_background_slot_uses_background_profile_binding() -> None:
    store, _ = _setup()
    resolver = StoreBackedProfileResolver(store)

    profile = resolver.resolve_profile("space", ProfileSlot.BACKGROUND)

    assert profile.profile_id == "background-default"


def test_resolve_object_resolution_slot_uses_dedicated_profile_binding() -> None:
    store, _ = _setup()
    resolver = StoreBackedProfileResolver(store)

    profile = resolver.resolve_profile("space", ProfileSlot.OBJECT_RESOLUTION)

    assert profile.profile_id == "object-resolution-default"
    assert profile.model == "object-resolution-model"


def test_missing_object_resolution_binding_does_not_fallback_to_operational() -> None:
    store, connection = _setup()
    connection.execute(
        "DELETE FROM memory_space_model_profiles "
        "WHERE memory_space_id = ? AND profile_slot = ?",
        ("space", "object_resolution"),
    )
    connection.commit()
    resolver = StoreBackedProfileResolver(store)

    with pytest.raises(MissingProfileError) as error:
        resolver.resolve_profile("space", ProfileSlot.OBJECT_RESOLUTION)

    assert error.value.code == "profile_missing"
    assert error.value.slot is ProfileSlot.OBJECT_RESOLUTION
    assert error.value.reason == "binding_missing"


def test_resolve_embedding_slot_uses_persisted_slot() -> None:
    store, _ = _setup()
    resolver = StoreBackedProfileResolver(store)

    profile = resolver.resolve_profile("space", ProfileSlot.EMBEDDING)

    assert profile.profile_id == "embedding-default"
    assert profile.model == "embed-model"


def test_missing_binding_raises_structured_error() -> None:
    store, _ = _setup()
    resolver = StoreBackedProfileResolver(store)

    with pytest.raises(MissingProfileError) as error:
        resolver.resolve_profile("unknown-space", ProfileSlot.OPERATIONAL)

    assert error.value.code == "profile_missing"
    assert error.value.slot is ProfileSlot.OPERATIONAL
    assert error.value.memory_space_id == "unknown-space"
    assert error.value.reason == "binding_missing"


def test_unbound_slot_raises_structured_error() -> None:
    store, connection = _setup()
    connection.execute(
        "DELETE FROM memory_space_model_profiles "
        "WHERE memory_space_id = ? AND profile_slot = ?",
        ("space", "operational"),
    )
    connection.commit()
    resolver = StoreBackedProfileResolver(store)

    with pytest.raises(MissingProfileError) as error:
        resolver.resolve_profile("space", ProfileSlot.OPERATIONAL)

    assert error.value.reason == "binding_missing"


def test_embedding_slot_without_configured_profile_raises() -> None:
    store, connection = _setup()
    connection.execute(
        "DELETE FROM memory_space_model_profiles "
        "WHERE memory_space_id = ? AND profile_slot = ?",
        ("space", "embedding"),
    )
    connection.commit()
    resolver = StoreBackedProfileResolver(store)

    with pytest.raises(MissingProfileError) as error:
        resolver.resolve_profile("space", ProfileSlot.EMBEDDING)

    assert error.value.reason == "binding_missing"


def test_missing_profile_row_raises_with_profile_id() -> None:
    store, _ = _setup()
    store.bind_slot("space", slot="operational", profile_id="missing-profile")
    resolver = StoreBackedProfileResolver(store)

    with pytest.raises(MissingProfileError) as error:
        resolver.resolve_profile("space", ProfileSlot.OPERATIONAL)

    assert error.value.reason == "profile_not_found"
    assert error.value.profile_id == "missing-profile"


def test_disabled_profile_raises_structured_error() -> None:
    store, connection = _setup()
    profile = store.get("operational-default")
    assert profile is not None
    store.upsert(profile.model_copy(update={"enabled": False}))
    connection.commit()
    resolver = StoreBackedProfileResolver(store)

    with pytest.raises(MissingProfileError) as error:
        resolver.resolve_profile("space", ProfileSlot.OPERATIONAL)

    assert error.value.reason == "profile_disabled"
    assert error.value.profile_id == "operational-default"


def test_slot_is_a_closed_string_vocabulary() -> None:
    assert ProfileSlot("operational") is ProfileSlot.OPERATIONAL
    assert ProfileSlot("background") is ProfileSlot.BACKGROUND
    assert ProfileSlot("object_resolution") is ProfileSlot.OBJECT_RESOLUTION
    assert ProfileSlot("embedding") is ProfileSlot.EMBEDDING
    assert str(ProfileSlot.EMBEDDING) == "embedding"
    with pytest.raises(ValueError):
        ProfileSlot("domain-facet")
