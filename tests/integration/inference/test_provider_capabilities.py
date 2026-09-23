from __future__ import annotations

import json
import sqlite3

from ledgermind_local import cli
from ledgermind_local.core_gateway.contracts import (
    CoreExecutionResult,
    CoreExecutionTask,
)
from ledgermind_local.inference.profile_store import InferenceProfileStore
from ledgermind_local.inference.profiles import InferenceProfile, ProviderCapabilities
from ledgermind_local.inference.provider_probe import ProviderProbeResult
from ledgermind_local.inference.secrets import SecretStore
from ledgermind_local.paths import ServicePaths
from ledgermind_local.persistence import open_sqlite_connection
from ledgermind_local.persistence import rounds_migrations as migrations
from ledgermind_local.production_support import (
    background_structured_output_preference,
)


def _profile() -> InferenceProfile:
    return InferenceProfile(
        profile_id="profile",
        base_url="https://provider.example/v1",
        model="model",
        secret_ref="provider-secret",
        structured_output_preference="tool_call",
        token_parameter="max_completion_tokens",
        supports_system_role=False,
        supports_seed=True,
    )


def test_background_structured_output_preference_prefers_json_schema() -> None:
    assert (
        background_structured_output_preference(("json_object", "json_schema", "prompt_only"))
        == "json_schema"
    )
    assert (
        background_structured_output_preference(("json_object", "prompt_only"))
        == "json_object"
    )
    assert background_structured_output_preference(("prompt_only",)) == "prompt_only"
    assert background_structured_output_preference(()) == "auto"


def test_migration_and_capability_persistence_are_restart_safe(tmp_path) -> None:
    database = tmp_path / "rounds.db"
    connection = open_sqlite_connection(database)
    try:
        migrations.apply_migrations(connection)
        profile = _profile()
        store = InferenceProfileStore(connection)
        store.upsert(profile)
        stored = store.upsert_capabilities(
            ProviderCapabilities(
                profile_id=profile.profile_id,
                structured_output_mode="tool_call",
                tool_call_supported=True,
                probe_contract_digest="sha256:" + "b" * 64,
                probe_status="passed",
                last_probed_at="2026-08-09T00:00:00+00:00",
            )
        )
        connection.commit()
        assert store.get(profile.profile_id) == profile
        assert store.get_capabilities(profile.profile_id) == stored
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(inference_provider_capabilities)"
            )
        }
        assert {
            "profile_id",
            "structured_output_mode",
            "json_schema_supported",
            "tool_call_supported",
            "json_object_supported",
            "prompt_only_supported",
            "probe_contract_digest",
            "probe_status",
            "last_probed_at",
            "last_error_code",
        } <= columns
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()[0] == 14
    finally:
        connection.close()

    restarted = sqlite3.connect(database)
    restarted.row_factory = sqlite3.Row
    try:
        migrations.apply_migrations(restarted)
        assert InferenceProfileStore(restarted).get_capabilities("profile") == stored
    finally:
        restarted.close()


def test_ipc_metadata_roundtrip_and_opaque_operation() -> None:
    task_payload = {
        "schema_version": 2,
        "task_id": "task",
        "task_kind": "generate_json",
        "operation": "core-owned-operation",
        "profile_slot": "operational",
        "memory_space_id": "space",
        "expires_at": "2026-08-09T00:00:00Z",
        "lease": None,
        "model_request": {
            "messages": [{"role": "user", "content": "opaque"}],
            "max_output_tokens": 20,
            "output_contract": {
                "contract_name": "technical",
                "schema_digest": "sha256:" + "c" * 64,
                "json_schema": {},
            },
            "mode": "auto",
            "tool_name": "submit_result",
            "metadata": {"source": "core"},
        },
        "embedding_request": None,
        "operation_input": {"facet": "must-remain-opaque"},
    }
    task = CoreExecutionTask.from_payload(task_payload)
    assert task.to_payload()["model_request"] == task_payload["model_request"]
    result = CoreExecutionResult(
        task_id=task.task_id,
        task_kind="generate_json",
        status="completed",
        operation=task.operation,
        operation_input=task.operation_input,
        output={"ok": True},
        embedding_result=None,
        egress_audit={"status": "completed"},
        raw_model_text='```json\n{"ok":true}\n```',
        structured_output_mode="tool_call",
        contract_digest="sha256:" + "c" * 64,
        metadata={"finish_reason": "tool_calls"},
    )
    restored = CoreExecutionResult.from_payload(result.to_payload())
    assert restored.raw_model_text == result.raw_model_text
    assert restored.structured_output_mode == "tool_call"
    assert restored.contract_digest == result.contract_digest
    assert restored.metadata == result.metadata
    assert restored.operation == "core-owned-operation"
    assert restored.operation_input == {"facet": "must-remain-opaque"}


def test_probe_cli_emits_json_and_persists_selected_mode(tmp_path, monkeypatch, capsys) -> None:
    home = tmp_path / "local"
    assert cli.main(
        ["--home", str(home), "init", "--semantic-language", "ru"]
    ) == 0
    capsys.readouterr()
    paths = ServicePaths(home)
    connection = open_sqlite_connection(paths.rounds_database_file)
    try:
        migrations.apply_migrations(connection)
        connection.execute(
            "INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) "
            "VALUES ('space', 'tests', '2026-08-09T00:00:00Z', '2026-08-09T00:00:00Z')"
        )
        store = InferenceProfileStore(connection)
        store.upsert(_profile())
        store.bind_slot("space", slot="operational", profile_id="profile")
        connection.commit()
    finally:
        connection.close()
    SecretStore(paths.resolve_home_path("secrets.json")).put(
        "provider-secret", "TOP_SECRET"
    )

    class _Probe:
        def __init__(self, **kwargs: object) -> None:
            self.store = kwargs["capability_store"]

        def probe(self, memory_space_id: str, slot: str, **_kwargs: object) -> ProviderProbeResult:
            capabilities = ProviderCapabilities(
                profile_id="profile",
                structured_output_mode="tool_call",
                tool_call_supported=True,
                probe_contract_digest="sha256:" + "d" * 64,
                probe_status="passed",
            )
            self.store.upsert_capabilities(capabilities)
            return ProviderProbeResult(
                profile_id="profile",
                slot=slot,
                probe_kind=slot,
                status="passed",
                selected_mode="tool_call",
                attempted_modes=("json_schema", "tool_call"),
                capabilities=capabilities,
                contract_digest=capabilities.probe_contract_digest or "",
            )

    monkeypatch.setattr(cli, "ProviderProbe", _Probe)
    assert (
        cli.main(
            [
                "--home",
                str(home),
                "inference",
                "probe",
                "--memory-space-id",
                "space",
                "--slot",
                "operational",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_mode"] == "tool_call"
    check = sqlite3.connect(paths.rounds_database_file)
    try:
        assert check.execute(
            "SELECT structured_output_mode FROM inference_provider_capabilities "
            "WHERE profile_id = 'profile'"
        ).fetchone()[0] == "tool_call"
    finally:
        check.close()
