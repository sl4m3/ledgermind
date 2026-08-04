use std::fmt;

use serde::{Deserialize, Deserializer, Serialize, de::Error as DeError};

use crate::DomainError;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum EvidenceRelation {
    Origin,
    Supports,
    Contradicts,
    Refines,
}

impl EvidenceRelation {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Origin => "origin",
            Self::Supports => "supports",
            Self::Contradicts => "contradicts",
            Self::Refines => "refines",
        }
    }
}

impl<'de> Deserialize<'de> for EvidenceRelation {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        match String::deserialize(deserializer)?.as_str() {
            "origin" => Ok(Self::Origin),
            "supports" => Ok(Self::Supports),
            "contradicts" => Ok(Self::Contradicts),
            "refines" => Ok(Self::Refines),
            value => Err(D::Error::custom(format!(
                "unknown evidence relation: {value}"
            ))),
        }
    }
}

impl fmt::Display for EvidenceRelation {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct KnowledgeEvidence {
    knowledge_id: crate::KnowledgeId,
    hypothesis_id: crate::HypothesisId,
    relation: EvidenceRelation,
    created_at: time::OffsetDateTime,
}

impl KnowledgeEvidence {
    pub fn new(
        knowledge_id: crate::KnowledgeId,
        hypothesis_id: crate::HypothesisId,
        relation: EvidenceRelation,
        created_at: time::OffsetDateTime,
    ) -> Self {
        Self {
            knowledge_id,
            hypothesis_id,
            relation,
            created_at,
        }
    }

    pub fn knowledge_id(&self) -> &crate::KnowledgeId {
        &self.knowledge_id
    }

    pub fn hypothesis_id(&self) -> &crate::HypothesisId {
        &self.hypothesis_id
    }

    pub const fn relation(&self) -> EvidenceRelation {
        self.relation
    }

    pub const fn created_at(&self) -> time::OffsetDateTime {
        self.created_at
    }
}

pub type EvidenceLink = KnowledgeEvidence;

pub fn assert_has_origin_relation(evidences: &[KnowledgeEvidence]) -> Result<(), DomainError> {
    if evidences
        .iter()
        .any(|evidence| evidence.relation == EvidenceRelation::Origin)
    {
        Ok(())
    } else {
        Err(DomainError::MissingOriginEvidence)
    }
}
