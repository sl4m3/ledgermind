from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledgermind_protocol.core_ipc import (
    CORE_IPC_CAPABILITIES,
    CORE_IPC_ERROR_CODES,
    CORE_IPC_OPERATIONS,
    CORE_KNOWLEDGE_SCHEMA_VERSION,
    BackupManifestPayload,
    BeginRestorePayload,
    BeginRestoreResultPayload,
    CommitRestorePayload,
    CommitRestoreResultPayload,
    CoreError,
    CoreRequestEnvelope,
    CoreResponseEnvelope,
    CreateBackupPayload,
    HandshakeResultPayload,
    PrepareRestorePayload,
    PrepareRestoreResultPayload,
    RollbackRestorePayload,
    RollbackRestoreResultPayload,
    ValidateBackupPayload,
)

_SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas" / "core-ipc"
_SCHEMA_NAMES = {
    "handshake.schema.json",
    "request-envelope.schema.json",
    "response-envelope.schema.json",
    "error.schema.json",
    "create-backup.schema.json",
    "validate-backup.schema.json",
    "prepare-restore.schema.json",
    "begin-restore.schema.json",
    "commit-restore.schema.json",
    "rollback-restore.schema.json",
}


def test_core_ipc_schema_inventory_is_complete() -> None:
    assert {path.name for path in _SCHEMA_ROOT.glob("*.json")} == _SCHEMA_NAMES


def test_request_envelope_round_trips_canonical_json() -> None:
    envelope = CoreRequestEnvelope(
        protocol_version=1,
        request_id="request-1",
        operation="health",
        payload={"verbose": False},
    )

    encoded = envelope.to_json()

    assert encoded == (
        '{"operation":"health","payload":{"verbose":false},'
        '"protocol_version":1,"request_id":"request-1"}'
    )
    assert CoreRequestEnvelope.from_json(encoded) == envelope


def test_response_error_has_closed_code_and_retryability() -> None:
    response = CoreResponseEnvelope.from_error(
        request_id="request-1",
        error=CoreError(
            code="STORAGE_UNAVAILABLE",
            message="storage unavailable",
            error_id="error-1",
            retryable=True,
        ),
    )

    decoded = json.loads(response.to_json())

    assert decoded["status"] == "error"
    assert decoded["error"]["retryable"] is True
    assert set(CORE_IPC_ERROR_CODES) >= {"STORAGE_UNAVAILABLE", "INTERNAL_ERROR"}
    assert CoreResponseEnvelope.from_json(response.to_json()) == response


def test_envelopes_reject_unsupported_versions_and_unknown_operations() -> None:
    with pytest.raises(ValueError, match="protocol version"):
        CoreRequestEnvelope(2, "request-1", "health", {}).to_json()

    with pytest.raises(ValueError, match="operation"):
        CoreRequestEnvelope(1, "request-1", "not-an-operation", {}).to_json()


def test_removed_projection_operations_are_not_part_of_core_ipc() -> None:
    for operation in ("poll_projection_events", "ack_projection_events"):
        with pytest.raises(ValueError, match="operation"):
            CoreRequestEnvelope(1, "request-1", operation, {})

    with pytest.raises(ValueError, match="error code"):
        CoreError("NOT_A_CORE_ERROR", "bad", "error-1", False)


def test_complete_core_operation_inventory_is_advertisable() -> None:
    assert CORE_IPC_OPERATIONS == frozenset(
        {
            "handshake",
            "health",
            "create_backup",
            "validate_backup",
            "prepare_restore",
            "begin_restore",
            "commit_restore",
            "rollback_restore",
            "ingest_raw_round",
            "poll_execution_tasks",
            "submit_execution_result",
            "fail_execution_task",
            "retrieve_context",
            "record_retrieval_outcome",
            "run_control_maintenance",
            "get_object_facet_statistics",
            "delete_memory_space",
            "shutdown",
        }
    )
    handshake = HandshakeResultPayload(
        protocol_version=1,
        core_version="0.1.0",
        knowledge_schema_version=CORE_KNOWLEDGE_SCHEMA_VERSION,
        supported_operations=tuple(sorted(CORE_IPC_OPERATIONS)),
        capabilities={name: True for name in CORE_IPC_CAPABILITIES},
    )
    payload = handshake.to_payload()
    assert payload["knowledge_schema_version"] == CORE_KNOWLEDGE_SCHEMA_VERSION
    assert CORE_KNOWLEDGE_SCHEMA_VERSION == 1
    capabilities = payload["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["core_owned_backup"] is True
    assert capabilities["coordinated_restore"] is True


def test_failure_and_backup_payloads_round_trip() -> None:
    validate = ValidateBackupPayload(
        relative_path="exchange/incoming/snapshot.sqlite",
        sha256="sha256:" + "a" * 64,
    )
    prepare = PrepareRestorePayload.from_payload(validate.to_payload())
    assert prepare.relative_path == validate.relative_path
    assert prepare.sha256 == validate.sha256

    manifest = BackupManifestPayload(
        relative_path="exchange/outgoing/snapshot.sqlite",
        sha256="sha256:" + "b" * 64,
        size_bytes=42,
        schema_version=CORE_KNOWLEDGE_SCHEMA_VERSION,
    )
    prepared = PrepareRestoreResultPayload(
        restore_token="token-1",
        relative_path="exchange/incoming/snapshot.sqlite",
        sha256=validate.sha256,
        size_bytes=42,
        schema_version=CORE_KNOWLEDGE_SCHEMA_VERSION,
        requires_restart=True,
    )
    assert BackupManifestPayload.from_payload(manifest.to_payload()) == manifest
    assert prepared.to_payload()["requires_restart"] is True
    assert CreateBackupPayload.from_payload({}).to_payload() == {}
    with pytest.raises(TypeError):
        CreateBackupPayload.from_payload([])


def test_restore_decoders_reject_unknown_fields() -> None:
    begin_payload = {
        "relative_path": "exchange/incoming/snapshot.bin",
        "sha256": "sha256:" + "a" * 64,
        "restore_token": "token-1",
    }
    with pytest.raises(ValueError, match="unknown fields"):
        BeginRestorePayload.from_payload({**begin_payload, "unexpected": True})

    with pytest.raises(ValueError, match="unknown fields"):
        CommitRestorePayload.from_payload(
            {"restore_transaction_id": "transaction-1", "unexpected": True}
        )
    with pytest.raises(ValueError, match="unknown fields"):
        RollbackRestorePayload.from_payload(
            {"restore_transaction_id": "transaction-1", "unexpected": True}
        )


def test_envelope_and_handshake_decoders_reject_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        CoreRequestEnvelope.from_payload(
            {
                "protocol_version": 1,
                "request_id": "request-1",
                "operation": "begin_restore",
                "payload": {},
                "unexpected": True,
            }
        )

    with pytest.raises(ValueError, match="unknown fields"):
        HandshakeResultPayload.from_payload(
            {
                "protocol_version": 1,
                "core_version": "0.1.0",
                "knowledge_schema_version": CORE_KNOWLEDGE_SCHEMA_VERSION,
                "supported_operations": sorted(CORE_IPC_OPERATIONS),
                "capabilities": {name: True for name in CORE_IPC_CAPABILITIES},
                "unexpected": True,
            }
        )


@pytest.mark.parametrize(
    "relative_path",
    [
        "../knowledge.db",
        "exchange/incoming/../../knowledge.db",
        "exchange/incoming\\..\\knowledge.db",
        "/tmp/knowledge.db",
    ],
)
def test_restore_payloads_reject_path_traversal(relative_path: str) -> None:
    with pytest.raises(ValueError):
        BeginRestorePayload(
            relative_path=relative_path,
            sha256="sha256:" + "a" * 64,
            restore_token="token-1",
        )


@pytest.mark.parametrize(
    "sha256",
    [
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "g" * 64,
        "sha256-" + "a" * 64,
    ],
)
def test_restore_payloads_reject_invalid_sha256(sha256: str) -> None:
    with pytest.raises(ValueError):
        BeginRestorePayload(
            relative_path="exchange/incoming/snapshot.bin",
            sha256=sha256,
            restore_token="token-1",
        )


def test_restore_retry_envelopes_keep_transaction_identity() -> None:
    begin = BeginRestorePayload(
        relative_path="exchange/incoming/snapshot.bin",
        sha256="sha256:" + "a" * 64,
        restore_token="token-1",
    )
    assert BeginRestorePayload.from_payload(begin.to_payload()) == begin

    commit = CommitRestorePayload("transaction-1")
    first_commit = CoreRequestEnvelope(1, "restore-commit-1", "commit_restore", commit.to_payload())
    retry_commit = CoreRequestEnvelope(1, "restore-commit-1", "commit_restore", commit.to_payload())
    assert first_commit.to_json() == retry_commit.to_json()

    rollback = RollbackRestorePayload("transaction-1")
    first_rollback = CoreRequestEnvelope(
        1, "restore-rollback-1", "rollback_restore", rollback.to_payload()
    )
    retry_rollback = CoreRequestEnvelope(
        1, "restore-rollback-1", "rollback_restore", rollback.to_payload()
    )
    assert first_rollback.to_json() == retry_rollback.to_json()

    begun = BeginRestoreResultPayload(
        relative_path="exchange/incoming/snapshot.bin",
        sha256="sha256:" + "a" * 64,
        size_bytes=10,
        schema_version=CORE_KNOWLEDGE_SCHEMA_VERSION,
        restore_transaction_id="transaction-1",
        state="applied_pending_commit",
    )
    assert BeginRestoreResultPayload.from_payload(begun.to_payload()) == begun

    committed = CommitRestoreResultPayload("transaction-1", True, "committed")
    rolled_back = RollbackRestoreResultPayload("transaction-1", True, "rolled_back")
    assert CommitRestoreResultPayload.from_payload(committed.to_payload()) == committed
    assert RollbackRestoreResultPayload.from_payload(rolled_back.to_payload()) == rolled_back

    with pytest.raises(ValueError):
        BeginRestorePayload("exchange/incoming/snapshot.bin", "sha256:" + "a" * 64, "")
    with pytest.raises(ValueError):
        CommitRestorePayload("")
    with pytest.raises(ValueError):
        RollbackRestorePayload("../transaction")


def test_restore_schemas_are_closed_objects() -> None:
    for schema_name in (
        "prepare-restore.schema.json",
        "begin-restore.schema.json",
        "commit-restore.schema.json",
        "rollback-restore.schema.json",
    ):
        schema = json.loads((_SCHEMA_ROOT / schema_name).read_text(encoding="utf-8"))
        assert schema["additionalProperties"] is False
