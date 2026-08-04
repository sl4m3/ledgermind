use ledgermind_domain::identifiers::{
    HypothesisId, IdempotencyKey, KnowledgeId, MemorySpaceId, ModelTaskId, ProjectionEventId,
    RevisionId, Sha256Digest,
};
use serde_json::json;

#[test]
fn typed_identifiers_are_distinct_public_types() {
    let memory_space = MemorySpaceId::try_from("space-1").unwrap();
    let hypothesis = HypothesisId::try_from("hyp-1").unwrap();
    let knowledge = KnowledgeId::try_from("knowledge-1").unwrap();
    let revision = RevisionId::try_from("revision-1").unwrap();
    let task = ModelTaskId::try_from("task-1").unwrap();
    let event = ProjectionEventId::try_from("event-1").unwrap();

    assert_eq!(memory_space.as_str(), "space-1");
    assert_eq!(hypothesis.as_str(), "hyp-1");
    assert_eq!(knowledge.as_str(), "knowledge-1");
    assert_eq!(revision.as_str(), "revision-1");
    assert_eq!(task.as_str(), "task-1");
    assert_eq!(event.as_str(), "event-1");
}

#[test]
fn identifiers_reject_empty_or_whitespace_values() {
    assert!(MemorySpaceId::try_from("").is_err());
    assert!(HypothesisId::try_from("  \n").is_err());
    assert!(KnowledgeId::try_from("").is_err());
    assert!(RevisionId::try_from(" ").is_err());
    assert!(ModelTaskId::try_from("").is_err());
    assert!(ProjectionEventId::try_from("\t").is_err());
}

#[test]
fn identifiers_serialize_as_validated_strings() {
    let value = MemorySpaceId::try_from("space-1").unwrap();
    let encoded = serde_json::to_value(&value).unwrap();
    assert_eq!(encoded, json!("space-1"));

    let decoded: MemorySpaceId = serde_json::from_value(encoded).unwrap();
    assert_eq!(decoded, value);
    assert!(serde_json::from_value::<MemorySpaceId>(json!("")).is_err());
}

#[test]
fn idempotency_key_requires_lowercase_sha256_digest() {
    let key = IdempotencyKey::try_from(format!("sha256:{}", "a".repeat(64))).unwrap();
    assert_eq!(key.as_str(), format!("sha256:{}", "a".repeat(64)));

    assert!(IdempotencyKey::try_from("sha256:ABC".to_owned()).is_err());
    assert!(IdempotencyKey::try_from("sha256:abcd".to_owned()).is_err());
    assert!(IdempotencyKey::try_from("not-a-digest".to_owned()).is_err());
}

#[test]
fn sha256_digest_is_deterministic_and_parseable() {
    let digest = Sha256Digest::from_bytes(b"hello");
    assert_eq!(
        digest.as_str(),
        "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    );

    let parsed = Sha256Digest::try_from(digest.as_str().to_owned()).unwrap();
    assert_eq!(parsed, digest);
    assert!(Sha256Digest::try_from("sha256:xyz".to_owned()).is_err());
}
