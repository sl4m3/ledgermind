from __future__ import annotations

import pytest
from ledgermind_local.core_gateway.contracts import (
    ControlMaintenanceResult,
    CoreExecutionResult,
    CoreExecutionTask,
    RecordRetrievalOutcomeCommand,
    RunControlMaintenanceCommand,
)
from ledgermind_local.inference.strict import strict_requirement_for_contract

_EXPIRES_AT = "2026-08-08T12:00:00Z"


def _task_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "task_id": "task-1",
        "task_kind": "generate_json",
        "operation": "core_owned_operation",
        "profile_slot": "operational",
        "memory_space_id": "space-1",
        "expires_at": _EXPIRES_AT,
        "lease": "2026-08-08T11:05:00Z",
        "model_request": {
            "messages": [{"role": "user", "content": "opaque input"}],
            "max_output_tokens": 100,
            "response_format": "json_object",
        },
        "embedding_request": None,
        "operation_input": {"domain": {"owned_by": "core"}},
        "structured_generation": {
            "root_task_id": "task-1",
            "attempt_number": 0,
            "attempt_kind": "primary",
            "contract_digest": "sha256:" + "a" * 64,
        },
    }


def _strict_semantic_task_payload() -> dict[str, object]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "integer", "enum": [1]},
            "objects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {},
                    "required": [],
                },
            },
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {},
                    "required": [],
                },
            },
        },
        "required": ["schema_version", "objects", "claims"],
    }
    contract = {
        "contract_name": "semantic",
        "schema_version": 1,
        "json_schema": schema,
        "schema_digest": "",
    }
    requirement = strict_requirement_for_contract(contract)
    contract["schema_digest"] = requirement["schema_digest"]
    requirement = strict_requirement_for_contract(contract)
    return {
        **_task_payload(),
        "operation": "user_semantic",
        "model_request": {
            "messages": [{"role": "user", "content": "return semantic JSON"}],
            "max_output_tokens": 100,
            "output_contract": contract,
            "structured_output_requirement": requirement,
            "mode": "strict_json_schema",
        },
        "structured_generation": {
            "root_task_id": "task-1",
            "attempt_number": 0,
            "attempt_kind": "primary",
            "contract_digest": contract["schema_digest"],
        },
    }


def test_execution_task_round_trip_preserves_opaque_operation_metadata() -> None:
    task = CoreExecutionTask.from_payload(_task_payload())

    assert task.task_kind == "generate_json"
    assert task.operation == "core_owned_operation"
    assert task.operation_input == {"domain": {"owned_by": "core"}}
    assert task.structured_generation is not None
    assert task.to_payload()["operation_input"] == {"domain": {"owned_by": "core"}}
    assert task.to_payload()["structured_generation"]["attempt_number"] == 0


def test_semantic_task_requires_strict_json_schema() -> None:
    payload = _strict_semantic_task_payload()
    task = CoreExecutionTask.from_payload(payload)
    assert task.to_payload()["model_request"]["mode"] == "strict_json_schema"

    legacy = dict(payload)
    legacy["model_request"] = {
        **payload["model_request"],
        "mode": "json_object",
        "structured_output_requirement": None,
    }
    with pytest.raises(ValueError, match="require mode=strict_json_schema"):
        CoreExecutionTask.from_payload(legacy)


def test_claim_operations_and_subject_query_embedding_are_wire_opaque() -> None:
    for operation in ("extract_claims", "resolve_subjects", "semantic_repair"):
        payload = _task_payload()
        payload["operation"] = operation
        payload["operation_input"] = {"claims": [], "coverage": []}
        task = CoreExecutionTask.from_payload(payload)
        assert task.operation == operation
        assert task.operation_input == {"claims": [], "coverage": []}

    payload = {
        "schema_version": 2,
        "task_id": "subject-task",
        "task_kind": "embed_texts",
        "operation": "embed_texts",
        "profile_slot": "embedding",
        "memory_space_id": "space-1",
        "expires_at": _EXPIRES_AT,
        "embedding_request": {
            "texts": ["language LocaleProvider"],
            "subject_refs": ["subject:language"],
            "purpose": "subject_query",
        },
    }
    task = CoreExecutionTask.from_payload(payload)
    assert task.embedding_request == payload["embedding_request"]
    assert task.to_payload()["embedding_request"] == payload["embedding_request"]

    with pytest.raises(ValueError, match="not supported"):
        CoreExecutionTask.from_payload(
            {
                **payload,
                "embedding_request": {
                    **payload["embedding_request"],
                    "purpose": "object_first",
                },
            }
        )


def test_execution_result_rejects_unknown_fields_and_invalid_shape() -> None:
    payload = {
        "task_id": "task-1",
        "task_kind": "generate_json",
        "status": "completed",
        "operation": "core_owned_operation",
        "operation_input": {},
        "output": {},
        "embedding_result": None,
        "egress_audit": {"status": "completed"},
        "error_code": None,
    }

    result = CoreExecutionResult.from_payload(payload)
    assert result.to_payload() == payload

    with pytest.raises(ValueError, match="unknown fields"):
        CoreExecutionResult.from_payload({**payload, "unexpected": True})
    with pytest.raises(ValueError, match="invalid output shape"):
        CoreExecutionResult.from_payload({**payload, "output": None})


def test_retrieval_outcome_requires_candidate_bound_delivery() -> None:
    with pytest.raises(ValueError, match="subset"):
        RecordRetrievalOutcomeCommand(
            request_id="outcome-request",
            retrieval_request_id="retrieval-request",
            candidate_value_ids=("candidate-1",),
            delivered_value_ids=("other-value",),
        )


def test_control_maintenance_accepts_core_consolidation_counter() -> None:
    payload = {
        "status": "completed",
        "memory_echoes_reconciled": 0,
        "stats_rebuilt": 0,
        "stale_jobs_recovered": 0,
        "findings_created": 0,
        "duplicate_object_findings": 0,
        "objects_consolidated": 0,
        "missing_card_embeddings": 0,
        "missing_facet_embeddings": 0,
        "integrity_errors": 0,
        "diagnostic_rows_deleted": 0,
        "terminal_task_rows_deleted": 0,
        "cleanup_candidate_count": 0,
    }

    result = ControlMaintenanceResult.from_payload(payload)

    assert result.objects_consolidated == 0


def test_control_maintenance_replay_is_explicit_and_bounded() -> None:
    default = RunControlMaintenanceCommand("maintenance")
    replay = RunControlMaintenanceCommand(
        "replay",
        retry_failed_round_semantic=True,
        retry_limit=7,
        retry_error_code="provider_capability_unverified",
        retry_memory_space_id="codex-default",
        automatic_recovery=True,
    )

    assert default.to_payload() == {}
    assert replay.to_payload() == {
        "retry_failed_round_semantic": True,
        "retry_limit": 7,
        "retry_error_code": "provider_capability_unverified",
        "retry_memory_space_id": "codex-default",
        "automatic_recovery": True,
    }
    with pytest.raises(ValueError, match="between 1 and 1000"):
        RunControlMaintenanceCommand("replay", retry_limit=0)
    with pytest.raises(ValueError, match="128"):
        RunControlMaintenanceCommand("replay", retry_error_code="x" * 129)
    with pytest.raises(ValueError, match="200"):
        RunControlMaintenanceCommand("replay", retry_memory_space_id="x" * 201)
    with pytest.raises(ValueError, match="requires"):
        RunControlMaintenanceCommand("replay", automatic_recovery=True)
