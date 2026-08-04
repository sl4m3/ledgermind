use serde::{Deserialize, Serialize};

use crate::{DomainError, DomainResult, KnowledgeId};

fn required(value: String, field: &'static str) -> DomainResult<String> {
    if value.trim().is_empty() {
        return Err(DomainError::EmptyField { field });
    }
    Ok(value)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MergeProposalInput {
    pub title: String,
    pub target: String,
    pub statement: String,
    pub rationale: String,
    pub preserved_references: Vec<KnowledgeId>,
    pub preserved_constraints: Vec<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "MergeProposalWire")]
pub struct MergeProposal {
    title: String,
    target: String,
    statement: String,
    rationale: String,
    preserved_references: Vec<KnowledgeId>,
    preserved_constraints: Vec<String>,
}

impl MergeProposal {
    pub fn new(input: MergeProposalInput) -> DomainResult<Self> {
        let title = required(input.title, "title")?;
        let target = required(input.target, "target")?;
        let statement = required(input.statement, "statement")?;
        if title.chars().count() > 240 {
            return Err(DomainError::FieldTooLong {
                field: "title",
                maximum: 240,
                actual: title.chars().count(),
            });
        }
        if target.chars().count() > 240 {
            return Err(DomainError::FieldTooLong {
                field: "target",
                maximum: 240,
                actual: target.chars().count(),
            });
        }
        let preserved_constraints = input
            .preserved_constraints
            .into_iter()
            .map(|constraint| required(constraint, "preserved_constraint"))
            .collect::<DomainResult<Vec<_>>>()?;

        Ok(Self {
            title,
            target,
            statement,
            rationale: input.rationale,
            preserved_references: input.preserved_references,
            preserved_constraints,
        })
    }

    pub fn title(&self) -> &str {
        &self.title
    }

    pub fn target(&self) -> &str {
        &self.target
    }

    pub fn statement(&self) -> &str {
        &self.statement
    }

    pub fn rationale(&self) -> &str {
        &self.rationale
    }

    pub fn preserved_references(&self) -> &[KnowledgeId] {
        &self.preserved_references
    }

    pub fn preserved_constraints(&self) -> &[String] {
        &self.preserved_constraints
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct MergeProposalWire {
    title: String,
    target: String,
    statement: String,
    rationale: String,
    preserved_references: Vec<KnowledgeId>,
    preserved_constraints: Vec<String>,
}

impl TryFrom<MergeProposalWire> for MergeProposal {
    type Error = DomainError;

    fn try_from(value: MergeProposalWire) -> Result<Self, Self::Error> {
        Self::new(MergeProposalInput {
            title: value.title,
            target: value.target,
            statement: value.statement,
            rationale: value.rationale,
            preserved_references: value.preserved_references,
            preserved_constraints: value.preserved_constraints,
        })
    }
}
