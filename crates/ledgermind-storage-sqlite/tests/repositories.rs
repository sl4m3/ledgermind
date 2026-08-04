use ledgermind_application::{
    ContextUsageRecord, ContextUsageRepository, EvidenceRepository, HypothesisRepository,
    IdempotencyRepository, KnowledgeRepository, ModelTaskRecord, ModelTaskRepository,
    ProjectionEventRecord, ProjectionEventRepository, RevisionRepository, StoredIdempotencyResult,
};
use ledgermind_domain::{
    EvidenceLink, EvidenceRelation, Hypothesis, HypothesisEvidence, HypothesisExtraction,
    HypothesisId, HypothesisInput, IdempotencyKey, KnowledgeId, KnowledgeInput, KnowledgeItem,
    KnowledgeRevision, MemorySpaceId, ModelTaskId, Phase, ProjectionEventId, RevisionId,
    Sha256Digest,
};
use ledgermind_storage_sqlite::{Database, SqliteRepositories};
use rusqlite::params;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};

fn setup_database() -> (Database, MemorySpaceId) {
    let mut database = Database::open_in_memory().expect("database opens");
    database.migrate().expect("database migrates");
    let memory_space_id = MemorySpaceId::try_from("space-1").expect("valid space id");
    seed_memory_space(&mut database, &memory_space_id);
    (database, memory_space_id)
}

fn seed_memory_space(database: &mut Database, memory_space_id: &MemorySpaceId) {
    let timestamp = OffsetDateTime::from_unix_timestamp(1_700_000_000).expect("valid timestamp");
    let timestamp = timestamp.format(&Rfc3339).expect("timestamp formats");
    database
        .connection_mut()
        .execute(
            "INSERT INTO memory_spaces
                (memory_space_id, display_name, source_client, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?4)",
            params![memory_space_id.as_str(), "Test", "test", timestamp],
        )
        .expect("memory space inserts");
}

fn sample_hypothesis(memory_space_id: &MemorySpaceId) -> Hypothesis {
    sample_hypothesis_with_id(memory_space_id, "hypothesis-1")
}

fn sample_hypothesis_with_id(memory_space_id: &MemorySpaceId, hypothesis_id: &str) -> Hypothesis {
    Hypothesis::new(HypothesisInput {
        hypothesis_id: HypothesisId::try_from(hypothesis_id).expect("valid hypothesis id"),
        memory_space_id: memory_space_id.clone(),
        content_digest: Sha256Digest::from_bytes(b"content"),
        title: "A title".to_owned(),
        target: "A target".to_owned(),
        statement: "A statement".to_owned(),
        rationale: "A rationale".to_owned(),
        result: "A result".to_owned(),
        artifacts: vec!["artifact.md".to_owned()],
        evidence: HypothesisEvidence::new(
            "local",
            "instance-1",
            "profile-1",
            "session-1",
            "round-1",
            Sha256Digest::from_bytes(b"raw"),
            Sha256Digest::from_bytes(b"normalized"),
            vec![ProjectionEventId::try_from("event-1").expect("valid event id")],
        )
        .expect("valid evidence"),
        extraction: HypothesisExtraction::new(
            "provider",
            "model",
            1,
            1,
            OffsetDateTime::from_unix_timestamp(1_700_000_001).expect("valid timestamp"),
        )
        .expect("valid extraction"),
        created_at: OffsetDateTime::from_unix_timestamp(1_700_000_002).expect("valid timestamp"),
    })
    .expect("valid hypothesis")
}

#[test]
fn hypothesis_repository_round_trips_and_enforces_memory_space_scope() {
    let (database, memory_space_id) = setup_database();
    let hypothesis = sample_hypothesis(&memory_space_id);
    let repositories = SqliteRepositories::new(database.connection());

    repositories
        .hypotheses()
        .add(&hypothesis)
        .expect("hypothesis inserts");

    let loaded = repositories
        .hypotheses()
        .get(&memory_space_id, hypothesis.id())
        .expect("hypothesis loads")
        .expect("hypothesis exists");
    assert_eq!(loaded, hypothesis);

    let other_space = MemorySpaceId::try_from("space-2").expect("valid other space");
    assert!(
        repositories
            .hypotheses()
            .get(&other_space, hypothesis.id())
            .expect("scoped lookup succeeds")
            .is_none()
    );
}

fn sample_knowledge(memory_space_id: &MemorySpaceId, knowledge_id: &str) -> KnowledgeItem {
    KnowledgeItem::new(KnowledgeInput {
        knowledge_id: KnowledgeId::try_from(knowledge_id).expect("valid knowledge id"),
        memory_space_id: memory_space_id.clone(),
        title: "Knowledge title".to_owned(),
        target: "Knowledge target".to_owned(),
        statement: "Knowledge statement".to_owned(),
        rationale: "Knowledge rationale".to_owned(),
        phase: Phase::Pattern,
        version: 1,
        created_at: OffsetDateTime::from_unix_timestamp(1_700_000_010).expect("valid timestamp"),
        updated_at: OffsetDateTime::from_unix_timestamp(1_700_000_010).expect("valid timestamp"),
        superseded_by_id: None,
        deleted_at: None,
    })
    .expect("valid knowledge item")
}

#[test]
fn knowledge_revision_and_evidence_repositories_preserve_invariants() {
    let (mut database, memory_space_id) = setup_database();
    let other_space = MemorySpaceId::try_from("space-2").expect("valid other space");
    seed_memory_space(&mut database, &other_space);
    let hypothesis = sample_hypothesis(&memory_space_id);
    let knowledge = sample_knowledge(&memory_space_id, "knowledge-1");
    let successor = sample_knowledge(&memory_space_id, "knowledge-2");
    let repositories = SqliteRepositories::new(database.connection());

    repositories
        .hypotheses()
        .add(&hypothesis)
        .expect("hypothesis inserts");
    repositories
        .knowledge()
        .add(&knowledge)
        .expect("knowledge inserts");
    repositories
        .knowledge()
        .add(&successor)
        .expect("successor inserts");

    let revision = KnowledgeRevision::from_snapshot(
        RevisionId::try_from("revision-1").expect("valid revision id"),
        knowledge.id().clone(),
        knowledge.version(),
        "created".to_owned(),
        serde_json::json!({"statement": knowledge.statement(), "version": 1}),
        Some(hypothesis.id().clone()),
        OffsetDateTime::from_unix_timestamp(1_700_000_011).expect("valid timestamp"),
    )
    .expect("valid revision");
    repositories
        .revisions()
        .add(&revision)
        .expect("revision inserts");

    let link = EvidenceLink::new(
        knowledge.id().clone(),
        hypothesis.id().clone(),
        EvidenceRelation::Origin,
        OffsetDateTime::from_unix_timestamp(1_700_000_012).expect("valid timestamp"),
    );
    repositories
        .evidence()
        .add(&link)
        .expect("evidence inserts");

    assert_eq!(
        repositories
            .knowledge()
            .get(&memory_space_id, knowledge.id())
            .unwrap(),
        Some(knowledge.clone())
    );
    assert_eq!(
        repositories
            .revisions()
            .list_for_knowledge(&memory_space_id, knowledge.id())
            .unwrap(),
        vec![revision]
    );
    assert_eq!(
        repositories
            .evidence()
            .count_for_knowledge(&memory_space_id, knowledge.id())
            .unwrap(),
        1
    );
    assert_eq!(
        repositories
            .evidence()
            .list_for_knowledge(&memory_space_id, knowledge.id())
            .unwrap(),
        vec![link]
    );

    let current_revision: String = database
        .connection()
        .query_row(
            "SELECT current_revision_id FROM knowledge_items WHERE knowledge_id = ?1",
            [knowledge.id().as_str()],
            |row| row.get(0),
        )
        .expect("current revision is stored");
    assert_eq!(current_revision, "revision-1");

    let updated = knowledge
        .with_superseded_by(
            successor.id().clone(),
            OffsetDateTime::from_unix_timestamp(1_700_000_013).expect("valid timestamp"),
        )
        .expect("valid supersession");
    repositories
        .knowledge()
        .update(&updated, knowledge.version())
        .expect("optimistic update succeeds");
    assert!(
        repositories
            .knowledge()
            .get(&memory_space_id, knowledge.id())
            .unwrap()
            .unwrap()
            .superseded_by_id()
            .is_some()
    );

    let stale_error = repositories
        .knowledge()
        .update(&knowledge, knowledge.version())
        .expect_err("stale update must fail");
    assert!(matches!(
        stale_error,
        ledgermind_storage_sqlite::StorageError::VersionConflict { .. }
    ));

    let other_hypothesis = sample_hypothesis_with_id(&other_space, "hypothesis-2");
    repositories
        .hypotheses()
        .add(&other_hypothesis)
        .expect("other hypothesis inserts");
    let cross_space_link = EvidenceLink::new(
        knowledge.id().clone(),
        other_hypothesis.id().clone(),
        EvidenceRelation::Supports,
        OffsetDateTime::from_unix_timestamp(1_700_000_014).expect("valid timestamp"),
    );
    let error = repositories
        .evidence()
        .add(&cross_space_link)
        .expect_err("cross-space link must fail");
    assert!(matches!(
        error,
        ledgermind_storage_sqlite::StorageError::Integrity(_)
    ));
}

#[test]
fn supporting_repositories_round_trip_and_reject_idempotency_conflicts() {
    let (database, memory_space_id) = setup_database();
    let repositories = SqliteRepositories::new(database.connection());
    let timestamp = OffsetDateTime::from_unix_timestamp(1_700_000_020).expect("valid timestamp");
    let key = IdempotencyKey::try_from(
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    .expect("valid idempotency key");
    let request_hash = Sha256Digest::from_bytes(b"request");
    let result = StoredIdempotencyResult {
        memory_space_id: memory_space_id.clone(),
        idempotency_key: key.clone(),
        request_hash: request_hash.clone(),
        response_json: "{\"accepted\":true}".to_owned(),
        created_at: timestamp,
        expires_at: None,
    };
    repositories
        .idempotency()
        .put(&result)
        .expect("idempotency result inserts");
    repositories
        .idempotency()
        .put(&result)
        .expect("same idempotency result replays");
    assert_eq!(
        repositories
            .idempotency()
            .get(&memory_space_id, &key)
            .unwrap(),
        Some(result.clone())
    );

    let conflicting = StoredIdempotencyResult {
        request_hash: Sha256Digest::from_bytes(b"different request"),
        response_json: "{\"accepted\":false}".to_owned(),
        ..result
    };
    let error = repositories
        .idempotency()
        .put(&conflicting)
        .expect_err("same key with another request must fail");
    assert!(matches!(
        error,
        ledgermind_storage_sqlite::StorageError::IdempotencyConflict { .. }
    ));

    let task = ModelTaskRecord {
        task_id: ModelTaskId::try_from("task-1").expect("valid task id"),
        memory_space_id: memory_space_id.clone(),
        task_type: "merge_knowledge".to_owned(),
        status: "queued".to_owned(),
        request_digest: Sha256Digest::from_bytes(b"task request"),
        payload_json: "{\"knowledge_ids\":[]}".to_owned(),
        result_json: None,
        created_at: timestamp,
        updated_at: timestamp,
        expires_at: Some(timestamp + time::Duration::hours(1)),
        lease_owner: None,
        lease_expires_at: None,
        attempts: 0,
    };
    repositories
        .model_tasks()
        .add(&task)
        .expect("model task inserts");
    assert_eq!(
        repositories
            .model_tasks()
            .get(&memory_space_id, &task.task_id)
            .unwrap(),
        Some(task.clone())
    );

    let event = ProjectionEventRecord {
        projection_event_id: ProjectionEventId::try_from("projection-event-1")
            .expect("valid projection event id"),
        memory_space_id: memory_space_id.clone(),
        aggregate_id: "knowledge-1".to_owned(),
        event_type: "knowledge.created".to_owned(),
        payload_json: "{\"knowledge_id\":\"knowledge-1\"}".to_owned(),
        occurred_at: timestamp,
    };
    repositories
        .projection_events()
        .add(&event)
        .expect("projection event inserts");
    assert_eq!(
        repositories
            .projection_events()
            .list_for_memory_space(&memory_space_id)
            .unwrap(),
        vec![event]
    );

    let usage = ContextUsageRecord {
        usage_id: "usage-1".to_owned(),
        memory_space_id: memory_space_id.clone(),
        knowledge_id: None,
        surface: "context.retrieve".to_owned(),
        metadata_json: "{\"limit\":5}".to_owned(),
        used_at: timestamp,
    };
    repositories
        .context_usage()
        .add(&usage)
        .expect("context usage inserts");
    assert_eq!(
        repositories
            .context_usage()
            .list_for_memory_space(&memory_space_id)
            .unwrap(),
        vec![usage]
    );
}

#[test]
fn model_task_lease_and_result_submission_are_scoped_and_idempotent() {
    let (database, memory_space_id) = setup_database();
    let timestamp = OffsetDateTime::from_unix_timestamp(1_700_000_100).unwrap();
    let task = ModelTaskRecord {
        task_id: ModelTaskId::try_from("lease-task-1").unwrap(),
        memory_space_id: memory_space_id.clone(),
        task_type: "merge_knowledge".to_owned(),
        status: "queued".to_owned(),
        request_digest: Sha256Digest::from_bytes(b"lease request"),
        payload_json: "{\"task_id\":\"lease-task-1\"}".to_owned(),
        result_json: None,
        created_at: timestamp,
        updated_at: timestamp,
        expires_at: Some(timestamp + time::Duration::hours(1)),
        lease_owner: None,
        lease_expires_at: None,
        attempts: 0,
    };
    let repositories = SqliteRepositories::new(database.connection());
    repositories.model_tasks().add(&task).unwrap();

    let (claimed, has_more) = repositories
        .model_tasks()
        .claim_for_worker(
            &memory_space_id,
            "worker-a",
            timestamp,
            time::Duration::seconds(60),
            10,
        )
        .unwrap();
    assert!(!has_more);
    assert_eq!(claimed.len(), 1);
    assert_eq!(claimed[0].status, "leased");
    assert_eq!(claimed[0].lease_owner.as_deref(), Some("worker-a"));
    assert_eq!(claimed[0].attempts, 1);

    let (other_claim, _) = repositories
        .model_tasks()
        .claim_for_worker(
            &memory_space_id,
            "worker-b",
            timestamp,
            time::Duration::seconds(60),
            10,
        )
        .unwrap();
    assert!(other_claim.is_empty());

    let wrong_owner = repositories
        .model_tasks()
        .submit_result(
            &memory_space_id,
            &task.task_id,
            "worker-b",
            "{\"title\":\"Merged\"}".to_owned(),
            timestamp,
        )
        .unwrap_err();
    assert!(matches!(
        wrong_owner,
        ledgermind_storage_sqlite::StorageError::StaleModelTask(_)
    ));

    let first = repositories
        .model_tasks()
        .submit_result(
            &memory_space_id,
            &task.task_id,
            "worker-a",
            "{\"title\":\"Merged\"}".to_owned(),
            timestamp,
        )
        .unwrap();
    assert!(first.accepted);
    assert!(!first.duplicate);
    assert_eq!(first.status, "completed");

    let replay = repositories
        .model_tasks()
        .submit_result(
            &memory_space_id,
            &task.task_id,
            "worker-a",
            "{\"title\":\"Merged\"}".to_owned(),
            timestamp,
        )
        .unwrap();
    assert!(replay.accepted);
    assert!(replay.duplicate);

    let conflict = repositories
        .model_tasks()
        .submit_result(
            &memory_space_id,
            &task.task_id,
            "worker-a",
            "{\"title\":\"Different\"}".to_owned(),
            timestamp,
        )
        .unwrap_err();
    assert!(matches!(
        conflict,
        ledgermind_storage_sqlite::StorageError::IdempotencyConflict { .. }
    ));
}

#[test]
fn projection_events_poll_until_ack_and_keep_consumer_state_independent() {
    let (database, memory_space_id) = setup_database();
    let repositories = SqliteRepositories::new(database.connection());
    let first = ProjectionEventRecord {
        projection_event_id: ProjectionEventId::try_from("projection-event-1").unwrap(),
        memory_space_id: memory_space_id.clone(),
        aggregate_id: "knowledge-1".to_owned(),
        event_type: "knowledge_projection_upsert".to_owned(),
        payload_json: r#"{"knowledge_id":"knowledge-1","memory_space_id":"space-1","title":"Title","target":"Target","statement":"Statement","projection_version":1}"#.to_owned(),
        occurred_at: OffsetDateTime::from_unix_timestamp(1_700_000_020).unwrap(),
    };
    let second = ProjectionEventRecord {
        projection_event_id: ProjectionEventId::try_from("projection-event-2").unwrap(),
        memory_space_id: memory_space_id.clone(),
        aggregate_id: "knowledge-2".to_owned(),
        event_type: "knowledge_projection_upsert".to_owned(),
        payload_json: r#"{"knowledge_id":"knowledge-2","memory_space_id":"space-1","title":"Title 2","target":"Target","statement":"Statement 2","projection_version":1}"#.to_owned(),
        occurred_at: OffsetDateTime::from_unix_timestamp(1_700_000_021).unwrap(),
    };
    repositories.projection_events().add(&first).unwrap();
    repositories.projection_events().add(&second).unwrap();

    let (events, has_more) = repositories
        .projection_events()
        .list_for_consumer(&memory_space_id, "local", None, 1)
        .unwrap();
    assert_eq!(events, vec![first.clone()]);
    assert!(has_more);

    let (after_first, has_more) = repositories
        .projection_events()
        .list_for_consumer(
            &memory_space_id,
            "other-local",
            Some(&first.projection_event_id),
            10,
        )
        .unwrap();
    assert_eq!(after_first, vec![second.clone()]);
    assert!(!has_more);

    let (repeat, _) = repositories
        .projection_events()
        .list_for_consumer(&memory_space_id, "other-local", None, 10)
        .unwrap();
    assert_eq!(repeat, vec![first.clone(), second.clone()]);

    repositories
        .projection_events()
        .acknowledge("local", std::slice::from_ref(&first.projection_event_id))
        .unwrap();
    let (remaining, has_more) = repositories
        .projection_events()
        .list_for_consumer(&memory_space_id, "local", None, 10)
        .unwrap();
    assert_eq!(remaining, vec![second]);
    assert!(!has_more);
}
