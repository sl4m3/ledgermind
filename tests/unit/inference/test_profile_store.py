from __future__ import annotations

import sqlite3

import pytest

from ledgermind_local.inference.profile_store import InferenceProfileStore
from ledgermind_local.inference.profiles import InferenceProfile
from ledgermind_local.persistence import rounds_migrations as migrations


def _profile(profile_id: str = "operational-default") -> InferenceProfile:
    return InferenceProfile(
        profile_id=profile_id,
        base_url="https://provider.example/v1",
        model="test-model",
        secret_ref="provider-main",
    )


def _connection(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    migrations.apply_migrations(connection)
    connection.execute(
        "INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("space", "tests", "2026-08-03T00:00:00+00:00", "2026-08-03T00:00:00+00:00"),
    )
    connection.commit()
    return connection


def test_profile_store_upserts_and_lists_without_secret_values(tmp_path) -> None:
    connection = _connection(tmp_path / "local.db")
    try:
        store = InferenceProfileStore(connection)
        store.upsert(_profile())
        assert store.get("operational-default") == _profile()
        assert store.list_ids() == ("operational-default",)
        row = connection.execute("SELECT * FROM inference_profiles").fetchone()
        assert row["secret_ref"] == "provider-main"
        assert "TOP_SECRET" not in " ".join(str(value) for value in row)
    finally:
        connection.close()


def test_profile_store_roundtrips_secret_free_provider_options(tmp_path) -> None:
    connection = _connection(tmp_path / "local.db")
    try:
        profile = _profile().model_copy(
            update={"extra_body": {"reasoning": {"effort": "none", "exclude": True}}}
        )
        store = InferenceProfileStore(connection)
        store.upsert(profile)
        assert store.get(profile.profile_id) == profile
        assert connection.execute(
            "SELECT extra_body_json FROM inference_profiles WHERE profile_id = ?",
            (profile.profile_id,),
        ).fetchone()[0] == '{"reasoning":{"effort":"none","exclude":true}}'
    finally:
        connection.close()


def test_profile_store_binds_technical_slots_and_records_safe_audit(tmp_path) -> None:
    connection = _connection(tmp_path / "local.db")
    try:
        store = InferenceProfileStore(connection)
        store.upsert(_profile())
        store.bind_slot("space", slot="operational", profile_id="operational-default")
        assert store.get_slot("space", "operational") == "operational-default"

        store.record_egress_audit(
            audit_id="audit-1",
            memory_space_id="space",
            profile_id="operational-default",
            operation="generate_json",
            provider_kind="openai_compatible",
            model="test-model",
            status="success",
            request_bytes=10,
            response_bytes=20,
            attempts=1,
        )
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(egress_audit)")
        ]
        assert "payload" not in columns
        assert (
            connection.execute("SELECT COUNT(*) FROM egress_audit").fetchone()[0] == 1
        )
    finally:
        connection.close()


def test_profile_store_rejects_binding_to_missing_profile(tmp_path) -> None:
    connection = _connection(tmp_path / "local.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            InferenceProfileStore(connection).bind_slot(
                "space", slot="operational", profile_id="missing"
            )
    finally:
        connection.close()


def test_profile_store_binds_generic_model_slots(tmp_path) -> None:
    connection = _connection(tmp_path / "local.db")
    try:
        store = InferenceProfileStore(connection)
        store.upsert(_profile("operational"))
        store.bind_slot("space", slot="operational", profile_id="operational")
        assert store.get_slot("space", "operational") == "operational"
        assert store.list_slots("space") == {"operational": "operational"}
    finally:
        connection.close()
