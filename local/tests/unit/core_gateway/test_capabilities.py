from __future__ import annotations

import pytest

from ledgermind_local.core_gateway.compatibility import (
    SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
    SUPPORTED_PROTOCOL_MAX,
)
from ledgermind_local.core_gateway.contracts import (
    CoreCapabilityError,
    IngestRawRoundCommand,
    TransientCoreError,
)
from ledgermind_local.core_gateway.process import (
    ProcessCoreGateway,
    _normalize_core_retrieval_payload,
)

_OPERATIONS = [
    "handshake",
    "health",
    "ingest_raw_round",
    "poll_execution_tasks",
    "submit_execution_result",
    "fail_execution_task",
    "retrieve_context",
    "record_retrieval_outcome",
    "run_control_maintenance",
    "get_object_facet_statistics",
    "delete_memory_space",
    "create_backup",
    "validate_backup",
    "prepare_restore",
    "begin_restore",
    "commit_restore",
    "rollback_restore",
    "shutdown",
]


class _Supervisor:
    def __init__(self, *, capabilities: dict[str, bool] | None = None) -> None:
        self.started = 0
        self.closed = 0
        self.requests: list[tuple[str, dict[str, object]]] = []
        self.handshake_result = {
            "protocol_version": SUPPORTED_PROTOCOL_MAX,
            "knowledge_schema_version": SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
            "supported_operations": list(_OPERATIONS),
            "capabilities": capabilities
            or {
            "core_owned_backup": True,
            "coordinated_restore": True,
            },
        }

    def start(self) -> None:
        self.started += 1

    def close(self) -> None:
        self.closed += 1

    def request(self, operation: str, payload: dict[str, object], *, request_id: str):
        del request_id
        self.requests.append((operation, payload))
        if operation == "ingest_raw_round":
            return {
                "raw_round_id": "core-round-1",
                "duplicate": False,
                "status": "accepted",
            }
        raise AssertionError(f"unexpected request: {operation}")


def test_process_gateway_accepts_current_core_schema() -> None:
    supervisor = _Supervisor()

    gateway = ProcessCoreGateway(
        supervisor,  # type: ignore[arg-type]
        required_capabilities=("base",),
    )

    assert gateway.advertised_schema_version == SUPPORTED_KNOWLEDGE_SCHEMA_MAX


def test_core_retrieval_provenance_is_removed_before_public_validation() -> None:
    payload = {
        "schema_version": 3,
        "retrieval_request_id": "retrieval-1",
        "items": [
            {
                "value_id": "value-1",
                "source_kind": "explicit_user",
            }
        ],
    }

    normalized = _normalize_core_retrieval_payload(payload)

    assert normalized["items"] == [{"value_id": "value-1"}]
    assert payload["items"][0]["source_kind"] == "explicit_user"


def test_process_gateway_forwards_embedding_profile_on_ingest() -> None:
    supervisor = _Supervisor()
    gateway = ProcessCoreGateway(supervisor)  # type: ignore[arg-type]
    profile = {
        "embedding_model_id": "embedder",
        "embedding_model_version": "sha256:" + "a" * 64,
        "embedding_profile_fingerprint": "sha256:" + "a" * 64,
        "embedding_profile_model_version": "api:embedder",
        "embedding_profile_digest_algorithm": "sha256",
        "embedding_profile_digest_algorithm_schema_version": 1,
        "embedding_dimensions": 3,
    }

    result = gateway.ingest_raw_round(
        IngestRawRoundCommand(
            command_id="command-1",
            idempotency_key="sha256:" + "b" * 64,
            memory_space_id="space-1",
            raw_round_id="round-1",
            raw_round={},
            embedding_profile=profile,
        )
    )

    assert result.accepted is True
    assert supervisor.requests[0][1]["embedding_profile"] == profile


def test_process_gateway_fails_closed_with_exact_schema_reason() -> None:
    supervisor = _Supervisor()
    supervisor.handshake_result["knowledge_schema_version"] = (
        SUPPORTED_KNOWLEDGE_SCHEMA_MAX + 1
    )

    with pytest.raises(CoreCapabilityError) as error:
        ProcessCoreGateway(
            supervisor,  # type: ignore[arg-type]
            required_capabilities=("base",),
        )

    assert error.value.reason_code == "core_knowledge_schema_incompatible"
    assert supervisor.closed == 1


def test_process_gateway_fails_closed_with_exact_protocol_reason() -> None:
    supervisor = _Supervisor()
    supervisor.handshake_result["protocol_version"] = 2

    with pytest.raises(CoreCapabilityError) as error:
        ProcessCoreGateway(
            supervisor,  # type: ignore[arg-type]
            required_capabilities=("base",),
        )

    assert error.value.reason_code == "core_protocol_incompatible"
    assert supervisor.closed == 1


def test_process_gateway_validates_feature_capability_at_initialization() -> None:
    supervisor = _Supervisor()
    gateway = ProcessCoreGateway(
        supervisor,  # type: ignore[arg-type]
        required_capabilities=("maintenance",),
    )

    assert supervisor.started == 1
    assert "create_backup" in gateway.advertised_operations
    assert "core_owned_backup" in gateway.advertised_capabilities


def test_process_gateway_fails_closed_when_feature_flag_is_missing() -> None:
    supervisor = _Supervisor(
        capabilities={
            "core_owned_backup": False,
            "coordinated_restore": True,
        }
    )

    with pytest.raises(CoreCapabilityError) as error:
        ProcessCoreGateway(
            supervisor,  # type: ignore[arg-type]
            required_capabilities=("maintenance",),
        )

    assert error.value.missing_capabilities == ("core_owned_backup",)
    assert error.value.missing_operations == ()
    assert supervisor.closed == 1


def test_process_gateway_fails_closed_when_operation_is_missing() -> None:
    supervisor = _Supervisor()
    supervisor.handshake_result["supported_operations"] = [
        operation for operation in _OPERATIONS if operation != "prepare_restore"
    ]

    with pytest.raises(CoreCapabilityError) as error:
        ProcessCoreGateway(
            supervisor,  # type: ignore[arg-type]
            required_capabilities=("maintenance",),
        )

    assert error.value.missing_operations == ("prepare_restore",)
    assert supervisor.closed == 1


def test_process_gateway_closes_supervisor_on_malformed_handshake() -> None:
    supervisor = _Supervisor()
    supervisor.handshake_result["supported_operations"] = "malformed"

    with pytest.raises(TransientCoreError, match="operations are malformed"):
        ProcessCoreGateway(
            supervisor,  # type: ignore[arg-type]
            required_capabilities=("maintenance",),
        )

    assert supervisor.started == 1
    assert supervisor.closed == 1
