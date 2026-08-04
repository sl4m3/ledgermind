use ledgermind_application::{
    CoreService, ModelTaskRecord, PollModelTasksRequest, PollProjectionEventsRequest,
    SubmitModelResultCommand,
};
use ledgermind_domain::{MemorySpaceId, ModelTaskId, Sha256Digest};
use ledgermind_storage_sqlite::{SqliteCoreService, StorageError};
use serde_json::json;
use time::{Duration, OffsetDateTime, format_description::well_known::Rfc3339};
use uuid::Uuid;

fn setup() -> (SqliteCoreService, MemorySpaceId, ModelTaskId) {
    let mut service = SqliteCoreService::open_in_memory().unwrap();
    let memory_space_id = MemorySpaceId::try_from("space-1").unwrap();
    let now = OffsetDateTime::now_utc();
    let expires_at = now + Duration::hours(1);
    {
        let connection = service.database().connection();
        connection
            .execute(
                "INSERT INTO memory_spaces(memory_space_id, display_name, source_client, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (
                    memory_space_id.as_str(),
                    "space-1",
                    "tests",
                    now.format(&Rfc3339).unwrap(),
                    now.format(&Rfc3339).unwrap(),
                ),
            )
            .unwrap();
        for (knowledge_id, title, version) in
            [("knowledge-a", "A", 1_i64), ("knowledge-b", "B", 1_i64)]
        {
            connection
                .execute(
                    "INSERT INTO knowledge_items(knowledge_id, memory_space_id, title, target, statement, rationale, phase, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        knowledge_id,
                        memory_space_id.as_str(),
                        title,
                        "ops",
                        format!("Statement {title}"),
                        "Rationale",
                        "pattern",
                        version,
                        now.format(&Rfc3339).unwrap(),
                        now.format(&Rfc3339).unwrap(),
                    ),
                )
                .unwrap();
        }
    }
    let task_id = ModelTaskId::from_uuid(Uuid::new_v4());
    let payload = json!({
        "task_id": task_id,
        "operation": "merge_knowledge",
        "memory_space_id": memory_space_id,
        "expected_versions": {"knowledge-a": 1, "knowledge-b": 1},
        "expires_at": expires_at.format(&Rfc3339).unwrap(),
        "model_input": {
            "items": [
                {"reference": "knowledge-a", "required_constraints": ["keep source"]},
                {"reference": "knowledge-b", "required_constraints": ["keep source"]}
            ]
        }
    });
    service
        .enqueue_model_task(&ModelTaskRecord {
            task_id: task_id.clone(),
            memory_space_id: memory_space_id.clone(),
            task_type: "merge_knowledge".to_owned(),
            status: "queued".to_owned(),
            request_digest: Sha256Digest::try_from(format!("sha256:{}", "a".repeat(64))).unwrap(),
            payload_json: serde_json::to_string(&payload).unwrap(),
            result_json: None,
            created_at: now,
            updated_at: now,
            expires_at: Some(expires_at),
            lease_owner: None,
            lease_expires_at: None,
            attempts: 0,
        })
        .unwrap();
    (service, memory_space_id, task_id)
}

fn poll(service: &mut SqliteCoreService, memory_space_id: &MemorySpaceId) {
    CoreService::poll_model_tasks(
        service,
        &PollModelTasksRequest {
            memory_space_id: memory_space_id.clone(),
            worker_id: "worker-1".to_owned(),
            limit: 1,
            lease_seconds: 300,
        },
    )
    .unwrap();
}

fn valid_result() -> String {
    serde_json::to_string(&json!({
        "title": "Merged",
        "target": "ops",
        "statement": "Combined statement",
        "rationale": "Agreement",
        "preserved_references": ["knowledge-a", "knowledge-b"],
        "preserved_constraints": ["keep source"]
    }))
    .unwrap()
}

fn submit(
    service: &mut SqliteCoreService,
    memory_space_id: &MemorySpaceId,
    task_id: &ModelTaskId,
    result_json: String,
) -> Result<ledgermind_application::SubmitModelResult, StorageError> {
    CoreService::submit_model_result(
        service,
        &SubmitModelResultCommand {
            task_id: task_id.clone(),
            memory_space_id: memory_space_id.clone(),
            worker_id: "worker-1".to_owned(),
            result_json,
        },
    )
}

#[test]
fn core_accepts_valid_merge_result_and_replays_same_result_idempotently() {
    let (mut service, memory_space_id, task_id) = setup();
    poll(&mut service, &memory_space_id);

    let first = submit(&mut service, &memory_space_id, &task_id, valid_result()).unwrap();
    let replay = submit(&mut service, &memory_space_id, &task_id, valid_result()).unwrap();

    assert!(first.accepted);
    assert!(!first.duplicate);
    assert!(replay.accepted);
    assert!(replay.duplicate);

    let connection = service.database().connection();
    let (successor_id, phase, version, superseded_by_id): (String, String, i64, Option<String>) =
        connection
            .query_row(
                "SELECT knowledge_id, phase, version, superseded_by_id
                 FROM knowledge_items
                 WHERE title = 'Merged'",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .unwrap();
    assert_eq!(phase, "emergent");
    assert_eq!(version, 1);
    assert!(superseded_by_id.is_none());
    for knowledge_id in ["knowledge-a", "knowledge-b"] {
        let (source_version, source_successor): (i64, String) = connection
            .query_row(
                "SELECT version, superseded_by_id FROM knowledge_items WHERE knowledge_id = ?",
                [knowledge_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .unwrap();
        assert_eq!(source_version, 2);
        assert_eq!(source_successor, successor_id);
    }
    assert_eq!(
        connection
            .query_row("SELECT COUNT(*) FROM knowledge_revisions", [], |row| {
                row.get::<_, i64>(0)
            })
            .unwrap(),
        3
    );
    assert_eq!(
        connection
            .query_row("SELECT COUNT(*) FROM supersession_links", [], |row| {
                row.get::<_, i64>(0)
            })
            .unwrap(),
        2
    );
    assert_eq!(
        connection
            .query_row("SELECT COUNT(*) FROM projection_events", [], |row| {
                row.get::<_, i64>(0)
            })
            .unwrap(),
        3
    );
    let projection_page = CoreService::poll_projection_events(
        &service,
        &PollProjectionEventsRequest {
            memory_space_id: memory_space_id.clone(),
            consumer_id: "local-fts".to_owned(),
            after_event_id: None,
            limit: 10,
        },
    )
    .unwrap();
    assert!(!projection_page.has_more);
    assert_eq!(projection_page.events.len(), 3);
    assert_eq!(
        projection_page
            .events
            .iter()
            .filter(|event| event.event_type == "knowledge_projection_delete")
            .count(),
        2
    );
    let upsert = projection_page
        .events
        .iter()
        .find(|event| event.event_type == "knowledge_projection_upsert")
        .unwrap();
    let upsert_payload: serde_json::Value = serde_json::from_str(&upsert.payload_json).unwrap();
    assert_eq!(upsert_payload["title"], "Merged");
    assert_eq!(upsert_payload["projection_version"], 1);
}

#[test]
fn core_rejects_merge_result_with_missing_reference() {
    let (mut service, memory_space_id, task_id) = setup();
    poll(&mut service, &memory_space_id);
    let result = json!({
        "title": "Merged",
        "target": "ops",
        "statement": "Combined statement",
        "rationale": "Agreement",
        "preserved_references": ["knowledge-a"],
        "preserved_constraints": ["keep source"]
    });

    let error = submit(
        &mut service,
        &memory_space_id,
        &task_id,
        serde_json::to_string(&result).unwrap(),
    )
    .unwrap_err();

    assert!(matches!(error, StorageError::InvalidRecord(_)));
}

#[test]
fn core_rejects_merge_result_after_expected_version_changes() {
    let (mut service, memory_space_id, task_id) = setup();
    poll(&mut service, &memory_space_id);
    service
        .database()
        .connection()
        .execute(
            "UPDATE knowledge_items SET version = 2 WHERE knowledge_id = 'knowledge-a'",
            [],
        )
        .unwrap();

    let error = submit(&mut service, &memory_space_id, &task_id, valid_result()).unwrap_err();

    assert!(matches!(error, StorageError::VersionConflict { .. }));
}
