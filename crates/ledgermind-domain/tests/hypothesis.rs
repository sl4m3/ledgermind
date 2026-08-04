use ledgermind_domain::hypothesis::{
    Hypothesis, HypothesisEvidence, HypothesisExtraction, HypothesisInput, HypothesisPayload,
};
use ledgermind_domain::{HypothesisId, MemorySpaceId, ProjectionEventId, Sha256Digest};
use time::{Duration, OffsetDateTime};

fn digest(byte: char) -> Sha256Digest {
    Sha256Digest::try_from(format!("sha256:{}", byte.to_string().repeat(64))).unwrap()
}

fn sample_input() -> HypothesisInput {
    HypothesisInput {
        hypothesis_id: HypothesisId::try_from("hyp-1").unwrap(),
        memory_space_id: MemorySpaceId::try_from("space-1").unwrap(),
        content_digest: digest('a'),
        title: "Use typed boundaries".to_owned(),
        target: "core".to_owned(),
        statement: "The Core owns knowledge.db".to_owned(),
        rationale: "It prevents split-brain ownership.".to_owned(),
        result: "Boundary remains explicit.".to_owned(),
        artifacts: vec!["ADR-0001".to_owned()],
        evidence: HypothesisEvidence::new(
            "hermes",
            "instance-1",
            "profile-1",
            "session-1",
            "round-1",
            digest('b'),
            digest('c'),
            vec![ProjectionEventId::try_from("event-1").unwrap()],
        )
        .unwrap(),
        extraction: HypothesisExtraction::new(
            "provider-1",
            "model-1",
            1,
            1,
            OffsetDateTime::UNIX_EPOCH,
        )
        .unwrap(),
        created_at: OffsetDateTime::UNIX_EPOCH + Duration::seconds(1),
    }
}

#[test]
fn hypothesis_is_immutable_and_preserves_typed_fields() {
    let hypothesis = Hypothesis::new(sample_input()).unwrap();

    assert_eq!(hypothesis.id().as_str(), "hyp-1");
    assert_eq!(hypothesis.memory_space_id().as_str(), "space-1");
    assert_eq!(hypothesis.title(), "Use typed boundaries");
    assert_eq!(hypothesis.evidence().source_event_ids().len(), 1);
    assert_eq!(hypothesis.extraction().prompt_version(), 1);

    let payload: HypothesisPayload = hypothesis.clone();
    assert_eq!(payload, hypothesis);
}

#[test]
fn hypothesis_round_trips_through_json_without_losing_contract_fields() {
    let hypothesis = Hypothesis::new(sample_input()).unwrap();
    let encoded = serde_json::to_string(&hypothesis).unwrap();
    let decoded: Hypothesis = serde_json::from_str(&encoded).unwrap();

    assert_eq!(decoded, hypothesis);
    assert!(encoded.contains("normalized_round_digest"));
    assert!(encoded.contains("source_event_ids"));
}

#[test]
fn hypothesis_rejects_empty_semantic_fields() {
    let mut input = sample_input();
    input.title = "  ".to_owned();
    assert!(Hypothesis::new(input).is_err());

    let mut input = sample_input();
    input.statement.clear();
    assert!(Hypothesis::new(input).is_err());
}

#[test]
fn evidence_and_extraction_reject_invalid_values() {
    assert!(
        HypothesisEvidence::new(
            "",
            "instance-1",
            "profile-1",
            "session-1",
            "round-1",
            digest('a'),
            digest('b'),
            vec![],
        )
        .is_err()
    );

    assert!(
        HypothesisExtraction::new("provider", "model", 0, 1, OffsetDateTime::UNIX_EPOCH,).is_err()
    );
}

#[test]
fn hypothesis_json_deserialization_reapplies_domain_validation() {
    let hypothesis = Hypothesis::new(sample_input()).unwrap();
    let mut encoded = serde_json::to_value(hypothesis).unwrap();
    encoded["title"] = serde_json::json!("");

    assert!(serde_json::from_value::<Hypothesis>(encoded).is_err());
}
