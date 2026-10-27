from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr

_LOCAL_ROOT = Path(__file__).resolve().parents[3]
if str(_LOCAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_LOCAL_ROOT))

from scripts.preproduction_local_core import (
    _config_for,
    _probe_generation_profiles,
    _seed_local,
)
from ledgermind_lab.config import default_config
from ledgermind_local.inference.profile_store import InferenceProfileStore
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.paths import ServicePaths


def test_preproduction_seeds_and_probes_distinct_generation_slots(monkeypatch, tmp_path) -> None:
    base = default_config()
    generation_base = base.generation.model_copy(update={"token": SecretStr("generation-token")})
    lab_config = base.model_copy(
        update={
            "generation": generation_base.model_copy(update={"model": "model-30b"}),
            "generation_profiles": {
                "object-resolution-profile": generation_base.model_copy(
                    update={"model": "model-120b"}
                ),
                "background-profile": generation_base.model_copy(
                    update={"model": "model-background"}
                ),
            },
            "execution_semantic_generation_profile": "background-profile",
            "object_resolution_generation_profile": "object-resolution-profile",
            "embedding": base.embedding.model_copy(
                update={"token": SecretStr("embedding-token")}
            ),
        }
    )
    home = tmp_path / "local"
    paths = ServicePaths(home)
    paths.home.mkdir(parents=True)
    config = _config_for(home=home, lab_config=lab_config, port=9876)
    _seed_local(
        paths=paths,
        config=config,
        lab_config=lab_config,
        memory_space_id="space",
    )
    database = paths.resolve_rounds_database_path(config.rounds_database_path)

    connection = open_sqlite_connection(database)
    try:
        store = InferenceProfileStore(connection)
        bindings = {
            slot: store.get_slot("space", slot)
            for slot in ("operational", "object_resolution", "background", "embedding")
        }
        profiles = {profile_id: store.get(profile_id) for profile_id in bindings.values()}
    finally:
        connection.close()

    assert bindings == {
        "operational": "generation-operational",
        "object_resolution": "generation-object-resolution",
        "background": "generation-background",
        "embedding": "embedding-api",
    }
    assert profiles["generation-operational"].model == "model-30b"
    assert profiles["generation-object-resolution"].model == "model-120b"
    assert profiles["generation-background"].model == "model-background"
    assert profiles["generation-operational"].extra_body["temperature"] == 0
    assert profiles["generation-object-resolution"].extra_body["temperature"] == 0
    assert profiles["generation-background"].extra_body["temperature"] == 0

    calls: list[str] = []

    class FakeProbe:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def probe(self, memory_space_id, slot, *, force, reprobe):
            del memory_space_id, force, reprobe
            calls.append(slot.value)
            return SimpleNamespace(
                selected_mode="strict_json_schema",
                status="passed",
                metadata={"cache_hit": False},
                capabilities=SimpleNamespace(
                    profile_fingerprint=f"fingerprint-{slot.value}",
                    probe_result="passed",
                ),
                error_code=None,
            )

    monkeypatch.setattr("scripts.preproduction_local_core.ProviderProbe", FakeProbe)
    report = _probe_generation_profiles(
        paths=paths,
        database=database,
        memory_space_id="space",
    )

    assert calls == ["operational", "object_resolution", "background"]
    assert report["object_resolution"]["profile_id"] == "generation-object-resolution"
    assert report["object_resolution"]["model"] == "model-120b"
    assert report["object_resolution"]["mode"] == "strict_json_schema"
    assert all(item["status"] == "passed" for item in report.values())
