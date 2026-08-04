use ledgermind_domain::KnowledgeId;
use ledgermind_domain::merge::{MergeProposal, MergeProposalInput};
use serde_json::json;

#[test]
fn merge_proposal_contains_only_model_returned_content() {
    let proposal = MergeProposal::new(MergeProposalInput {
        title: "Combined ownership rule".to_owned(),
        target: "core".to_owned(),
        statement: "Knowledge remains owned by Core".to_owned(),
        rationale: "The references agree.".to_owned(),
        preserved_references: vec![KnowledgeId::try_from("knowledge-1").unwrap()],
        preserved_constraints: vec!["no-local-knowledge-db".to_owned()],
    })
    .unwrap();

    assert_eq!(proposal.title(), "Combined ownership rule");
    assert_eq!(proposal.target(), "core");
    assert_eq!(proposal.preserved_references().len(), 1);
    assert_eq!(proposal.preserved_constraints(), &["no-local-knowledge-db"]);

    let json = serde_json::to_value(&proposal).unwrap();
    assert_eq!(json["title"], json!("Combined ownership rule"));
    assert!(json.get("phase").is_none());
    assert!(json.get("internal_actions").is_none());
}

#[test]
fn merge_proposal_rejects_empty_semantic_content() {
    let mut input = MergeProposalInput {
        title: "title".to_owned(),
        target: "target".to_owned(),
        statement: "statement".to_owned(),
        rationale: String::new(),
        preserved_references: vec![],
        preserved_constraints: vec![],
    };

    input.title.clear();
    assert!(MergeProposal::new(input.clone()).is_err());
    input.title = "title".to_owned();
    input.statement = " ".to_owned();
    assert!(MergeProposal::new(input).is_err());
}

#[test]
fn merge_json_deserialization_reapplies_domain_validation() {
    let proposal = MergeProposal::new(MergeProposalInput {
        title: "title".to_owned(),
        target: "target".to_owned(),
        statement: "statement".to_owned(),
        rationale: String::new(),
        preserved_references: vec![],
        preserved_constraints: vec![],
    })
    .unwrap();
    let mut encoded = serde_json::to_value(proposal).unwrap();
    encoded["title"] = json!("");

    assert!(serde_json::from_value::<MergeProposal>(encoded).is_err());
}
