use ledgermind_domain::evidence::{
    EvidenceLink, EvidenceRelation, KnowledgeEvidence, assert_has_origin_relation,
};
use ledgermind_domain::phase::Phase;
use ledgermind_domain::{HypothesisId, KnowledgeId};
use serde_json::json;
use time::OffsetDateTime;

#[test]
fn phase_values_are_closed_and_lowercase_serializable() {
    assert_eq!(Phase::Pattern.as_str(), "pattern");
    assert_eq!(Phase::Emergent.as_str(), "emergent");
    assert_eq!(Phase::Canonical.as_str(), "canonical");
    assert_eq!(
        serde_json::to_value(Phase::Canonical).unwrap(),
        json!("canonical")
    );
    assert_eq!(Phase::try_from("emergent").unwrap(), Phase::Emergent);
    assert!(Phase::try_from("vital").is_err());
}

#[test]
fn evidence_links_tie_knowledge_to_hypothesis() {
    let link = KnowledgeEvidence::new(
        KnowledgeId::try_from("knowledge-1").unwrap(),
        HypothesisId::try_from("hypothesis-1").unwrap(),
        EvidenceRelation::Origin,
        OffsetDateTime::UNIX_EPOCH,
    );

    assert_eq!(link.knowledge_id().as_str(), "knowledge-1");
    assert_eq!(link.hypothesis_id().as_str(), "hypothesis-1");
    assert_eq!(link.relation(), EvidenceRelation::Origin);

    let alias: EvidenceLink = link;
    assert_eq!(alias.relation(), EvidenceRelation::Origin);
}

#[test]
fn knowledge_creation_requires_origin_evidence() {
    let supporting = KnowledgeEvidence::new(
        KnowledgeId::try_from("knowledge-1").unwrap(),
        HypothesisId::try_from("hypothesis-1").unwrap(),
        EvidenceRelation::Supports,
        OffsetDateTime::UNIX_EPOCH,
    );
    assert_has_origin_relation(&[supporting]).unwrap_err();

    let origin = KnowledgeEvidence::new(
        KnowledgeId::try_from("knowledge-1").unwrap(),
        HypothesisId::try_from("hypothesis-2").unwrap(),
        EvidenceRelation::Origin,
        OffsetDateTime::UNIX_EPOCH,
    );
    assert_has_origin_relation(&[origin]).unwrap();
}
