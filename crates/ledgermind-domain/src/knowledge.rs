use serde::{Deserialize, Serialize};
use time::OffsetDateTime;

use crate::{DomainError, DomainResult, KnowledgeId, MemorySpaceId, Phase};

fn required(value: String, field: &'static str) -> DomainResult<String> {
    if value.trim().is_empty() {
        return Err(DomainError::EmptyField { field });
    }
    Ok(value)
}

fn next_version(version: u64) -> DomainResult<u64> {
    version.checked_add(1).ok_or(DomainError::InvalidVersion {
        field: "version",
        minimum: 1,
        actual: version,
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct KnowledgeInput {
    pub knowledge_id: KnowledgeId,
    pub memory_space_id: MemorySpaceId,
    pub title: String,
    pub target: String,
    pub statement: String,
    pub rationale: String,
    pub phase: Phase,
    pub version: u64,
    pub created_at: OffsetDateTime,
    pub updated_at: OffsetDateTime,
    pub superseded_by_id: Option<KnowledgeId>,
    pub deleted_at: Option<OffsetDateTime>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "KnowledgeItemWire")]
pub struct KnowledgeItem {
    knowledge_id: KnowledgeId,
    memory_space_id: MemorySpaceId,
    title: String,
    target: String,
    statement: String,
    rationale: String,
    phase: Phase,
    version: u64,
    created_at: OffsetDateTime,
    updated_at: OffsetDateTime,
    superseded_by_id: Option<KnowledgeId>,
    deleted_at: Option<OffsetDateTime>,
}

impl KnowledgeItem {
    pub fn new(input: KnowledgeInput) -> DomainResult<Self> {
        if input.version < 1 {
            return Err(DomainError::InvalidVersion {
                field: "version",
                minimum: 1,
                actual: input.version,
            });
        }
        if input.updated_at < input.created_at {
            return Err(DomainError::TimestampOrder);
        }
        if input.superseded_by_id.as_ref() == Some(&input.knowledge_id) {
            return Err(DomainError::SelfSupersession);
        }
        if input
            .deleted_at
            .is_some_and(|deleted_at| deleted_at < input.created_at)
        {
            return Err(DomainError::TimestampOrder);
        }

        let title = required(input.title, "title")?;
        if title.chars().count() > 240 {
            return Err(DomainError::FieldTooLong {
                field: "title",
                maximum: 240,
                actual: title.chars().count(),
            });
        }
        let target = required(input.target, "target")?;
        if target.chars().count() > 240 {
            return Err(DomainError::FieldTooLong {
                field: "target",
                maximum: 240,
                actual: target.chars().count(),
            });
        }

        Ok(Self {
            knowledge_id: input.knowledge_id,
            memory_space_id: input.memory_space_id,
            title,
            target,
            statement: required(input.statement, "statement")?,
            rationale: input.rationale,
            phase: input.phase,
            version: input.version,
            created_at: input.created_at,
            updated_at: input.updated_at,
            superseded_by_id: input.superseded_by_id,
            deleted_at: input.deleted_at,
        })
    }

    pub fn id(&self) -> &KnowledgeId {
        &self.knowledge_id
    }

    pub fn memory_space_id(&self) -> &MemorySpaceId {
        &self.memory_space_id
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

    pub const fn phase(&self) -> Phase {
        self.phase
    }

    pub const fn version(&self) -> u64 {
        self.version
    }

    pub const fn created_at(&self) -> OffsetDateTime {
        self.created_at
    }

    pub const fn updated_at(&self) -> OffsetDateTime {
        self.updated_at
    }

    pub fn superseded_by_id(&self) -> Option<&KnowledgeId> {
        self.superseded_by_id.as_ref()
    }

    pub const fn deleted_at(&self) -> Option<OffsetDateTime> {
        self.deleted_at
    }

    pub const fn is_current(&self) -> bool {
        self.superseded_by_id.is_none() && self.deleted_at.is_none()
    }

    pub fn with_superseded_by(
        &self,
        successor: KnowledgeId,
        updated_at: OffsetDateTime,
    ) -> DomainResult<Self> {
        if successor == self.knowledge_id {
            return Err(DomainError::SelfSupersession);
        }
        if self.superseded_by_id.is_some() {
            return Err(DomainError::AlreadySuperseded);
        }
        if updated_at < self.updated_at {
            return Err(DomainError::TimestampOrder);
        }

        Ok(Self {
            superseded_by_id: Some(successor),
            version: next_version(self.version)?,
            updated_at,
            ..self.clone()
        })
    }

    pub fn with_deleted_at(&self, deleted_at: OffsetDateTime) -> DomainResult<Self> {
        if deleted_at < self.updated_at {
            return Err(DomainError::TimestampOrder);
        }
        if self.deleted_at.is_some() {
            return Err(DomainError::AlreadyDeleted);
        }

        Ok(Self {
            deleted_at: Some(deleted_at),
            version: next_version(self.version)?,
            updated_at: deleted_at,
            ..self.clone()
        })
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct KnowledgeItemWire {
    knowledge_id: KnowledgeId,
    memory_space_id: MemorySpaceId,
    title: String,
    target: String,
    statement: String,
    rationale: String,
    phase: Phase,
    version: u64,
    created_at: OffsetDateTime,
    updated_at: OffsetDateTime,
    superseded_by_id: Option<KnowledgeId>,
    deleted_at: Option<OffsetDateTime>,
}

impl TryFrom<KnowledgeItemWire> for KnowledgeItem {
    type Error = DomainError;

    fn try_from(value: KnowledgeItemWire) -> Result<Self, Self::Error> {
        Self::new(KnowledgeInput {
            knowledge_id: value.knowledge_id,
            memory_space_id: value.memory_space_id,
            title: value.title,
            target: value.target,
            statement: value.statement,
            rationale: value.rationale,
            phase: value.phase,
            version: value.version,
            created_at: value.created_at,
            updated_at: value.updated_at,
            superseded_by_id: value.superseded_by_id,
            deleted_at: value.deleted_at,
        })
    }
}
