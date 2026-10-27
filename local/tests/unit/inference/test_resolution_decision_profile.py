import shutil

from ledgermind_local.inference.profile_store import InferenceProfileStore
from ledgermind_local.inference.profiles import InferenceProfile
from ledgermind_local.persistence import open_sqlite_connection, rounds_migrations


def test_upgrade_preserves_legacy_bindings_and_roundtrips_decision_backend(tmp_path):
    old = tmp_path / "old-migrations"
    old.mkdir()
    for file in rounds_migrations.MIGRATION_DIR.glob("*.sql"):
        if int(file.name[:4]) < 15:
            shutil.copyfile(file, old / file.name)
    connection = open_sqlite_connection(tmp_path / "rounds.db")
    try:
        rounds_migrations.apply_migrations(connection, old)
        connection.execute("INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) VALUES ('space', 'test', 'now', 'now')")
        store = InferenceProfileStore(connection)
        legacy = InferenceProfile(profile_id="legacy", base_url="https://provider.example/v1",
            model="generation", secret_ref="generation-api")
        connection.execute("INSERT INTO inference_profiles(profile_id, base_url, model, secret_ref, created_at, updated_at) VALUES ('legacy', 'https://provider.example/v1', 'generation', 'generation-api', 'now', 'now')")
        connection.execute("INSERT INTO memory_space_model_profiles VALUES ('space', 'operational', 'legacy', 'now')")
        connection.commit()
        rounds_migrations.apply_migrations(connection)
        assert store.get("legacy").model == legacy.model
        assert store.get_slot("space", "operational") == "legacy"
        decision = InferenceProfile(profile_id="decision", decision_backend="jev",
            base_url="https://openrouter.ai/api/alpha/decisions", model="typesafe/jev-1.13",
            secret_ref="decision-key")
        store.upsert(decision)
        store.bind_slot("space", slot="resolution_decision", profile_id="decision")
        assert store.get("decision") == decision
        assert store.get_slot("space", "resolution_decision") == "decision"
        rounds_migrations.apply_migrations(connection)
        assert store.get_slot("space", "operational") == "legacy"
    finally:
        connection.close()
