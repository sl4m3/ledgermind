use ledgermind_application::{AcceptHypothesisCommand, CoreService, RecordContextUsageCommand};
use ledgermind_domain::{
    Hypothesis, HypothesisEvidence, HypothesisExtraction, HypothesisId, HypothesisInput,
    IdempotencyKey, MemorySpaceId, ProjectionEventId, Sha256Digest,
};
use ledgermind_storage_sqlite::{SqliteCoreService, StorageError};
use time::OffsetDateTime;

fn hypothesis() -> Hypothesis {
    Hypothesis::new(HypothesisInput {
        hypothesis_id: HypothesisId::try_from("hypothesis-accept-1").unwrap(),
        memory_space_id: MemorySpaceId::try_from("memory-space-accept").unwrap(),
        content_digest: Sha256Digest::from_bytes(b"content"),
        title: "Accept title".to_owned(),
        target: "Rust Core".to_owned(),
        statement: "Rust Core accepts hypotheses atomically".to_owned(),
        rationale: "Stage 10 vertical slice".to_owned(),
        result: "accepted".to_owned(),
        artifacts: vec!["artifact".to_owned()],
        evidence: HypothesisEvidence::new(
            "local".to_owned(),
            "instance".to_owned(),
            "profile".to_owned(),
            "session".to_owned(),
            "round".to_owned(),
            Sha256Digest::from_bytes(b"raw-round"),
            Sha256Digest::from_bytes(b"normalized-round"),
            vec![ProjectionEventId::try_from("source-event-1").unwrap()],
        )
        .unwrap(),
        extraction: HypothesisExtraction::new(
            "provider".to_owned(),
            "model".to_owned(),
            1,
            1,
            OffsetDateTime::from_unix_timestamp(1_700_000_000).unwrap(),
        )
        .unwrap(),
        created_at: OffsetDateTime::from_unix_timestamp(1_700_000_000).unwrap(),
    })
    .unwrap()
}

fn command(request_hash: Sha256Digest) -> AcceptHypothesisCommand {
    AcceptHypothesisCommand {
        command_id: "command-accept-1".to_owned(),
        idempotency_key: IdempotencyKey::try_from(format!("sha256:{}", "ab".repeat(32))).unwrap(),
        request_hash,
        memory_space_id: MemorySpaceId::try_from("memory-space-accept").unwrap(),
        hypothesis: hypothesis(),
    }
}

#[test]
fn accept_hypothesis_is_atomic_idempotent_and_creates_minimal_projection() {
    let mut service = SqliteCoreService::open_in_memory().expect("service opens");
    let first = service
        .accept_hypothesis(&command(Sha256Digest::from_bytes(b"request-1")))
        .expect("first accept succeeds");
    assert!(first.accepted);
    assert!(!first.duplicate);
    assert!(first.core_reference_id.is_some());

    let duplicate = service
        .accept_hypothesis(&command(Sha256Digest::from_bytes(b"request-1")))
        .expect("replay succeeds");
    assert!(duplicate.duplicate);
    assert_eq!(duplicate.core_reference_id, first.core_reference_id);

    let conflict = service
        .accept_hypothesis(&command(Sha256Digest::from_bytes(b"request-2")))
        .expect_err("different payload hash must conflict");
    assert!(matches!(conflict, StorageError::IdempotencyConflict { .. }));

    let connection = service.database().connection();
    for (table, expected) in [
        ("hypotheses", 1_i64),
        ("knowledge_items", 1_i64),
        ("knowledge_revisions", 1_i64),
        ("evidence_links", 1_i64),
        ("projection_events", 1_i64),
        ("idempotency_results", 1_i64),
    ] {
        let count: i64 = connection
            .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| {
                row.get(0)
            })
            .unwrap();
        assert_eq!(count, expected, "unexpected {table} count");
    }
    let relation: String = connection
        .query_row("SELECT relation FROM evidence_links", [], |row| row.get(0))
        .unwrap();
    assert_eq!(relation, "origin");
}

#[test]
fn failed_context_usage_does_not_leave_an_orphan_memory_space() {
    let mut service = SqliteCoreService::open_in_memory().expect("service opens");
    let result = service.record_context_usage(&RecordContextUsageCommand {
        usage_id: "usage-rollback-1".to_owned(),
        memory_space_id: MemorySpaceId::try_from("memory-space-rollback").unwrap(),
        item_ids: vec![ledgermind_domain::KnowledgeId::try_from("missing-item").unwrap()],
        used_at: OffsetDateTime::from_unix_timestamp(1_700_000_000).unwrap(),
        session_id: None,
        round_id: None,
    });
    assert!(matches!(result, Err(StorageError::NotFound(_))));

    let count: i64 = service
        .database()
        .connection()
        .query_row(
            "SELECT COUNT(*) FROM memory_spaces WHERE memory_space_id = 'memory-space-rollback'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 0);
}
