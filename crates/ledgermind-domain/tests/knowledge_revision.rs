use ledgermind_domain::knowledge::{KnowledgeInput, KnowledgeItem};
use ledgermind_domain::revision::KnowledgeRevision;
use ledgermind_domain::{HypothesisId, KnowledgeId, MemorySpaceId, Phase, RevisionId};
use serde_json::json;
use time::{Duration, OffsetDateTime};

fn ids() -> (KnowledgeId, MemorySpaceId) {
    (
        KnowledgeId::try_from("knowledge-1").unwrap(),
        MemorySpaceId::try_from("space-1").unwrap(),
    )
}

fn sample_knowledge() -> KnowledgeItem {
    let (knowledge_id, memory_space_id) = ids();
    KnowledgeItem::new(KnowledgeInput {
        knowledge_id,
        memory_space_id,
        title: "Typed ownership".to_owned(),
        target: "core".to_owned(),
        statement: "Core owns knowledge.db".to_owned(),
        rationale: "One owner avoids split brain.".to_owned(),
        phase: Phase::Emergent,
        version: 1,
        created_at: OffsetDateTime::UNIX_EPOCH,
        updated_at: OffsetDateTime::UNIX_EPOCH,
        superseded_by_id: None,
        deleted_at: None,
    })
    .unwrap()
}

#[test]
fn knowledge_item_exposes_current_phase_and_version() {
    let knowledge = sample_knowledge();
    assert_eq!(knowledge.id().as_str(), "knowledge-1");
    assert_eq!(knowledge.memory_space_id().as_str(), "space-1");
    assert_eq!(knowledge.phase(), Phase::Emergent);
    assert_eq!(knowledge.version(), 1);
    assert!(knowledge.is_current());
}

#[test]
fn supersession_creates_a_new_version_and_marks_item_non_current() {
    let knowledge = sample_knowledge();
    let successor = KnowledgeId::try_from("knowledge-2").unwrap();
    let superseded = knowledge
        .with_superseded_by(
            successor.clone(),
            OffsetDateTime::UNIX_EPOCH + Duration::seconds(1),
        )
        .unwrap();

    assert_eq!(superseded.superseded_by_id(), Some(&successor));
    assert_eq!(superseded.version(), 2);
    assert!(!superseded.is_current());
    assert!(knowledge.is_current());
}

#[test]
fn knowledge_item_rejects_invalid_state() {
    let mut input = KnowledgeInput {
        knowledge_id: ids().0,
        memory_space_id: ids().1,
        title: "title".to_owned(),
        target: "target".to_owned(),
        statement: "statement".to_owned(),
        rationale: String::new(),
        phase: Phase::Pattern,
        version: 0,
        created_at: OffsetDateTime::UNIX_EPOCH,
        updated_at: OffsetDateTime::UNIX_EPOCH,
        superseded_by_id: None,
        deleted_at: None,
    };
    assert!(KnowledgeItem::new(input.clone()).is_err());

    input.version = 1;
    input.updated_at = OffsetDateTime::UNIX_EPOCH - Duration::seconds(1);
    assert!(KnowledgeItem::new(input).is_err());

    let knowledge = sample_knowledge();
    assert!(
        knowledge
            .with_superseded_by(knowledge.id().clone(), OffsetDateTime::UNIX_EPOCH)
            .is_err()
    );
}

#[test]
fn revision_canonicalizes_object_snapshot_with_sorted_keys() {
    let revision = KnowledgeRevision::from_snapshot(
        RevisionId::try_from("revision-1").unwrap(),
        KnowledgeId::try_from("knowledge-1").unwrap(),
        1,
        "knowledge.created".to_owned(),
        json!({"z": 2, "a": {"d": false, "c": true}}),
        Some(HypothesisId::try_from("hypothesis-1").unwrap()),
        OffsetDateTime::UNIX_EPOCH,
    )
    .unwrap();

    assert_eq!(
        revision.snapshot_json(),
        r#"{"a":{"c":true,"d":false},"z":2}"#
    );
    assert_eq!(
        revision.snapshot(),
        &json!({"z": 2, "a": {"d": false, "c": true}})
    );
    assert_eq!(revision.version(), 1);
    assert_eq!(revision.event_type(), "knowledge.created");
}

#[test]
fn revision_rejects_non_object_or_invalid_snapshots() {
    assert!(
        KnowledgeRevision::from_snapshot(
            RevisionId::try_from("revision-1").unwrap(),
            KnowledgeId::try_from("knowledge-1").unwrap(),
            1,
            "event".to_owned(),
            json!([1, 2, 3]),
            None,
            OffsetDateTime::UNIX_EPOCH,
        )
        .is_err()
    );

    assert!(
        KnowledgeRevision::from_json(
            RevisionId::try_from("revision-1").unwrap(),
            KnowledgeId::try_from("knowledge-1").unwrap(),
            1,
            "event".to_owned(),
            "not-json".to_owned(),
            None,
            OffsetDateTime::UNIX_EPOCH,
        )
        .is_err()
    );
}

#[test]
fn knowledge_json_deserialization_reapplies_domain_validation() {
    let mut encoded = serde_json::to_value(sample_knowledge()).unwrap();
    encoded["version"] = json!(0);

    assert!(serde_json::from_value::<KnowledgeItem>(encoded).is_err());
}
