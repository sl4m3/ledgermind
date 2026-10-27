from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from ledgermind_local.inference.embedding_provider import PersistentEmbeddingCache
from ledgermind_local.inference.profile_store import InferenceProfileStore
from ledgermind_local.inference.profiles import InferenceProfile, ProviderCapabilities
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations


MIGRATION_SOURCE = Path(rounds_migrations.MIGRATION_DIR)


def _migration_dir(tmp_path: Path, through: int) -> Path:
    target = tmp_path / f"migrations-{through:04d}"
    target.mkdir()
    for path in sorted(MIGRATION_SOURCE.glob("*.sql")):
        if int(path.name[:4]) <= through:
            shutil.copy2(path, target / path.name)
    return target


@pytest.mark.parametrize("through", [0, 8, 9, 10, 11])
def test_migration_history_is_replayable_through_each_release_head(
    tmp_path: Path, through: int
) -> None:
    database = tmp_path / f"through-{through}.db"
    connection = open_sqlite_connection(database)
    try:
        migration_dir = _migration_dir(tmp_path, through)
        applied = rounds_migrations.apply_migrations(connection, migration_dir)
        expected = tuple(range(1, through + 1))
        assert tuple(migration.version for migration in applied) == expected
        schema_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'schema_migrations'"
        ).fetchone()
        actual = (
            tuple(
                int(row[0])
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                )
            )
            if schema_table is not None
            else ()
        )
        assert actual == expected
        if through >= 9:
            capability_columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(inference_provider_capabilities)"
                )
            }
            assert {
                "profile_fingerprint",
                "transport",
                "model",
                "detected_capabilities_json",
                "probe_result",
                "structured_json_schema",
                "max_output_tokens_known",
            } <= capability_columns
        if through >= 10:
            cache_columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(embedding_vector_cache)"
                )
            }
            assert {
                "cache_key",
                "profile_fingerprint",
                "cache_namespace",
                "content_digest",
                "dimensions",
                "vector_json",
                "created_at",
            } <= cache_columns
    finally:
        connection.close()


def test_capability_and_embedding_cache_survive_connection_restart(tmp_path: Path) -> None:
    database = tmp_path / "restart.db"
    connection = open_sqlite_connection(database)
    try:
        rounds_migrations.apply_migrations(connection)
        profile = InferenceProfile(
            profile_id="generation-operational",
            base_url="https://provider.example/v1",
            model="model",
            secret_ref="secret-ref",
        )
        store = InferenceProfileStore(connection)
        store.upsert(profile)
        capabilities = store.upsert_capabilities(
            ProviderCapabilities(
                profile_id=profile.profile_id,
                profile_fingerprint="sha256:" + "a" * 64,
                structured_output_mode="json_schema",
                json_schema_supported=True,
                probe_status="passed",
                probe_result="passed",
            )
        )
        connection.commit()
        assert store.get_capabilities(profile.profile_id) == capabilities
        cache = PersistentEmbeddingCache(database)
        cache.put(
            "sha256:cache-key",
            (0.1, 0.2, 0.3),
            profile_fingerprint="sha256:" + "b" * 64,
            namespace="facet_catalog",
            content_digest="sha256:" + "c" * 64,
        )
    finally:
        connection.close()

    restarted = sqlite3.connect(database)
    try:
        restarted.row_factory = sqlite3.Row
        rounds_migrations.apply_migrations(restarted)
        assert InferenceProfileStore(restarted).get_capabilities(
            "generation-operational"
        ) == capabilities
    finally:
        restarted.close()
    reopened_cache = PersistentEmbeddingCache(database)
    assert reopened_cache.get("sha256:cache-key") == (0.1, 0.2, 0.3)
