use std::collections::BTreeMap;

use ledgermind_domain::{HypothesisId, IdempotencyKey, MemorySpaceId};
use ledgermind_protocol::{
    AcceptHypothesisPayload, CoreError, CoreErrorCode, CoreRequestEnvelope, CoreResponseEnvelope,
    HandshakePayload, HypothesisEvidencePayload, HypothesisExtractionPayload, HypothesisPayload,
    ModelTaskPayload, Operation, PollModelTasksPayload, PollProjectionEventsPayload,
    ProjectionUpsertPayload, ProtocolError, RecordContextUsagePayload, SubmitModelResultPayload,
};

fn digest(byte: u8) -> String {
    format!("sha256:{}", format!("{byte:02x}").repeat(32))
}

fn hypothesis_payload() -> HypothesisPayload {
    HypothesisPayload {
        hypothesis_id: "hypothesis-1".to_owned(),
        content_digest: digest(1),
        title: "Title".to_owned(),
        target: "Target".to_owned(),
        statement: "Statement".to_owned(),
        rationale: "Rationale".to_owned(),
        result: "Result".to_owned(),
        artifacts: vec!["artifact".to_owned()],
        evidence: HypothesisEvidencePayload {
            source_system: "local".to_owned(),
            source_instance_id: "instance".to_owned(),
            source_profile_id: "profile".to_owned(),
            source_session_id: "session".to_owned(),
            source_round_id: "round".to_owned(),
            raw_round_digest: digest(2),
            normalized_round_digest: digest(3),
            source_event_ids: vec!["event-1".to_owned()],
        },
        extraction: HypothesisExtractionPayload {
            provider: "provider".to_owned(),
            model: "model".to_owned(),
            prompt_version: 1,
            schema_version: 1,
            completed_at: "2023-11-14T22:13:20Z".to_owned(),
        },
    }
}

#[test]
fn accept_payload_converts_to_typed_domain_input_and_envelope_round_trips() {
    let payload = AcceptHypothesisPayload {
        protocol_version: 1,
        command_id: "command-1".to_owned(),
        idempotency_key: digest(4),
        memory_space_id: "memory-space-1".to_owned(),
        hypothesis: hypothesis_payload(),
    };
    let input = payload.clone().into_domain().expect("payload is valid");
    assert_eq!(
        input.memory_space_id,
        MemorySpaceId::try_from("memory-space-1").unwrap()
    );
    assert_eq!(
        input.hypothesis.id(),
        &HypothesisId::try_from("hypothesis-1").unwrap()
    );
    assert_eq!(
        input.idempotency_key,
        IdempotencyKey::try_from(digest(4)).unwrap()
    );

    let envelope = CoreRequestEnvelope::new(
        "request-1",
        Operation::AcceptHypothesis,
        serde_json::to_value(payload).unwrap(),
    )
    .unwrap();
    let parsed = CoreRequestEnvelope::from_json(&envelope.to_json()).unwrap();
    assert_eq!(parsed.request_id, "request-1");
    assert_eq!(parsed.operation, Operation::AcceptHypothesis);
}

#[test]
fn envelopes_reject_wrong_version_unknown_fields_and_invalid_error_codes() {
    let error = CoreRequestEnvelope::from_json(
        r#"{"protocol_version": 99, "request_id": "request-1", "operation": "health", "payload": {}}"#,
    )
    .unwrap_err();
    assert!(matches!(error, ProtocolError::UnsupportedVersion(99)));

    let malformed = r#"{
        "protocol_version": 1,
        "request_id": "request-1",
        "operation": "health",
        "payload": {},
        "unexpected": true
    }"#;
    assert!(CoreRequestEnvelope::from_json(malformed).is_err());

    let invalid_error =
        CoreError::new(CoreErrorCode::InternalError, "failure", "error-1", false).unwrap();
    let response = CoreResponseEnvelope::error("request-1", invalid_error).unwrap();
    let parsed = CoreResponseEnvelope::from_json(&response.to_json()).unwrap();
    assert_eq!(parsed.request_id, "request-1");
}

#[test]
fn payload_validation_matches_schema_unique_items_constraints() {
    let handshake = HandshakePayload {
        client_name: "client".to_owned(),
        client_version: "1".to_owned(),
        supported_operations: vec![Operation::Health, Operation::Health],
        capabilities: serde_json::Map::new(),
    };
    assert!(handshake.validate().is_err());

    let usage = RecordContextUsagePayload {
        memory_space_id: "memory-space-1".to_owned(),
        item_ids: vec!["item-1".to_owned(), "item-1".to_owned()],
    };
    assert!(usage.into_domain().is_err());
}

#[test]
fn projection_payload_excludes_core_internal_fields_and_protocol_exposes_poll_ack() {
    let payload = ProjectionUpsertPayload {
        knowledge_id: "knowledge-1".to_owned(),
        memory_space_id: "space-1".to_owned(),
        title: "Title".to_owned(),
        target: "Target".to_owned(),
        statement: "Statement".to_owned(),
        projection_version: 1,
    };
    let json = serde_json::to_value(payload).unwrap();
    assert!(json.get("phase").is_none());
    assert!(json.get("evidence_count").is_none());
    assert!(
        serde_json::from_value::<ProjectionUpsertPayload>(serde_json::json!({
            "knowledge_id": "knowledge-1",
            "memory_space_id": "space-1",
            "title": "Title",
            "target": "Target",
            "statement": "Statement",
            "projection_version": 1,
            "phase": "canonical"
        }))
        .is_err()
    );

    let poll = PollProjectionEventsPayload {
        memory_space_id: "space-1".to_owned(),
        consumer_id: "local-projections".to_owned(),
        after_event_id: None,
        limit: 10,
    };
    assert_eq!(poll.limit, 10);
    assert_eq!(
        serde_json::to_string(&Operation::PollProjectionEvents).unwrap(),
        "\"poll_projection_events\""
    );
    assert_eq!(
        serde_json::to_string(&Operation::AckProjectionEvents).unwrap(),
        "\"ack_projection_events\""
    );
}

#[test]
fn model_task_contract_is_strict_and_bounded_for_poll_and_submit() {
    let task = ModelTaskPayload {
        task_id: "task-1".to_owned(),
        operation: "merge_knowledge".to_owned(),
        memory_space_id: "memory-space-1".to_owned(),
        expected_versions: BTreeMap::from([
            ("knowledge-a".to_owned(), 3),
            ("knowledge-b".to_owned(), 5),
        ]),
        expires_at: "2026-08-03T12:00:00Z".to_owned(),
        model_input: serde_json::json!({
            "items": [{
                "reference": "knowledge-a",
                "title": "A",
                "target": "ops",
                "statement": "A statement",
                "rationale": "A rationale",
                "required_constraints": ["keep source"]
            }]
        }),
        lease_expires_at: Some("2026-08-03T11:05:00Z".to_owned()),
    };
    let encoded = serde_json::to_value(&task).expect("task serializes");
    let decoded: ModelTaskPayload = serde_json::from_value(encoded).expect("task round trips");
    assert_eq!(decoded, task);
    assert!(
        serde_json::from_value::<ModelTaskPayload>(serde_json::json!({
            "task_id": "task-1",
            "operation": "merge_knowledge",
            "memory_space_id": "memory-space-1",
            "expected_versions": {"knowledge-a": 3},
            "expires_at": "2026-08-03T12:00:00Z",
            "model_input": {"items": []},
            "internal_phase": "pattern"
        }))
        .is_err()
    );

    let poll = PollModelTasksPayload {
        memory_space_id: "memory-space-1".to_owned(),
        worker_id: "local-model-tasks".to_owned(),
        limit: 10,
        lease_seconds: 60,
    };
    let envelope = CoreRequestEnvelope::new(
        "poll-model-tasks-1",
        Operation::PollModelTasks,
        serde_json::to_value(poll).unwrap(),
    )
    .unwrap();
    assert_eq!(
        CoreRequestEnvelope::from_json(&envelope.to_json())
            .unwrap()
            .operation,
        Operation::PollModelTasks
    );

    let submit = SubmitModelResultPayload {
        task_id: "task-1".to_owned(),
        memory_space_id: "memory-space-1".to_owned(),
        worker_id: "local-model-tasks".to_owned(),
        result: serde_json::json!({
            "title": "Merged",
            "target": "ops",
            "statement": "Merged statement",
            "rationale": "Merged rationale",
            "preserved_references": ["knowledge-a", "knowledge-b"],
            "preserved_constraints": ["keep source"]
        }),
    };
    let submit_envelope = CoreRequestEnvelope::new(
        "submit-model-result-1",
        Operation::SubmitModelResult,
        serde_json::to_value(submit).unwrap(),
    )
    .unwrap();
    assert_eq!(
        CoreRequestEnvelope::from_json(&submit_envelope.to_json())
            .unwrap()
            .operation,
        Operation::SubmitModelResult
    );
}
