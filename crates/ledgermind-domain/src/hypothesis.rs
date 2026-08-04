use serde::{Deserialize, Serialize};
use time::OffsetDateTime;

use crate::{
    DomainError, DomainResult, HypothesisId, MemorySpaceId, ProjectionEventId, Sha256Digest,
};

fn required(value: String, field: &'static str) -> DomainResult<String> {
    if value.trim().is_empty() {
        return Err(DomainError::EmptyField { field });
    }
    Ok(value)
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "HypothesisEvidenceWire")]
pub struct HypothesisEvidence {
    source_system: String,
    source_instance_id: String,
    source_profile_id: String,
    source_session_id: String,
    source_round_id: String,
    raw_round_digest: Sha256Digest,
    normalized_round_digest: Sha256Digest,
    source_event_ids: Vec<ProjectionEventId>,
}

impl HypothesisEvidence {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        source_system: impl Into<String>,
        source_instance_id: impl Into<String>,
        source_profile_id: impl Into<String>,
        source_session_id: impl Into<String>,
        source_round_id: impl Into<String>,
        raw_round_digest: Sha256Digest,
        normalized_round_digest: Sha256Digest,
        source_event_ids: Vec<ProjectionEventId>,
    ) -> DomainResult<Self> {
        Ok(Self {
            source_system: required(source_system.into(), "source_system")?,
            source_instance_id: required(source_instance_id.into(), "source_instance_id")?,
            source_profile_id: required(source_profile_id.into(), "source_profile_id")?,
            source_session_id: required(source_session_id.into(), "source_session_id")?,
            source_round_id: required(source_round_id.into(), "source_round_id")?,
            raw_round_digest,
            normalized_round_digest,
            source_event_ids,
        })
    }

    pub fn source_system(&self) -> &str {
        &self.source_system
    }

    pub fn source_instance_id(&self) -> &str {
        &self.source_instance_id
    }

    pub fn source_profile_id(&self) -> &str {
        &self.source_profile_id
    }

    pub fn source_session_id(&self) -> &str {
        &self.source_session_id
    }

    pub fn source_round_id(&self) -> &str {
        &self.source_round_id
    }

    pub fn raw_round_digest(&self) -> &Sha256Digest {
        &self.raw_round_digest
    }

    pub fn normalized_round_digest(&self) -> &Sha256Digest {
        &self.normalized_round_digest
    }

    pub fn source_event_ids(&self) -> &[ProjectionEventId] {
        &self.source_event_ids
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "HypothesisExtractionWire")]
pub struct HypothesisExtraction {
    provider: String,
    model: String,
    prompt_version: u32,
    schema_version: u32,
    completed_at: OffsetDateTime,
}

impl HypothesisExtraction {
    pub fn new(
        provider: impl Into<String>,
        model: impl Into<String>,
        prompt_version: u32,
        schema_version: u32,
        completed_at: OffsetDateTime,
    ) -> DomainResult<Self> {
        let prompt_version = u64::from(prompt_version);
        if prompt_version < 1 {
            return Err(DomainError::InvalidVersion {
                field: "prompt_version",
                minimum: 1,
                actual: prompt_version,
            });
        }
        let schema_version_u64 = u64::from(schema_version);
        if schema_version_u64 < 1 {
            return Err(DomainError::InvalidVersion {
                field: "schema_version",
                minimum: 1,
                actual: schema_version_u64,
            });
        }

        Ok(Self {
            provider: required(provider.into(), "provider")?,
            model: required(model.into(), "model")?,
            prompt_version: prompt_version as u32,
            schema_version,
            completed_at,
        })
    }

    pub fn provider(&self) -> &str {
        &self.provider
    }

    pub fn model(&self) -> &str {
        &self.model
    }

    pub fn prompt_version(&self) -> u32 {
        self.prompt_version
    }

    pub fn schema_version(&self) -> u32 {
        self.schema_version
    }

    pub fn completed_at(&self) -> OffsetDateTime {
        self.completed_at
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HypothesisInput {
    pub hypothesis_id: HypothesisId,
    pub memory_space_id: MemorySpaceId,
    pub content_digest: Sha256Digest,
    pub title: String,
    pub target: String,
    pub statement: String,
    pub rationale: String,
    pub result: String,
    pub artifacts: Vec<String>,
    pub evidence: HypothesisEvidence,
    pub extraction: HypothesisExtraction,
    pub created_at: OffsetDateTime,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "HypothesisWire")]
pub struct Hypothesis {
    hypothesis_id: HypothesisId,
    memory_space_id: MemorySpaceId,
    content_digest: Sha256Digest,
    title: String,
    target: String,
    statement: String,
    rationale: String,
    result: String,
    artifacts: Vec<String>,
    evidence: HypothesisEvidence,
    extraction: HypothesisExtraction,
    created_at: OffsetDateTime,
}

impl Hypothesis {
    pub fn new(input: HypothesisInput) -> DomainResult<Self> {
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
            hypothesis_id: input.hypothesis_id,
            memory_space_id: input.memory_space_id,
            content_digest: input.content_digest,
            title,
            target,
            statement: required(input.statement, "statement")?,
            rationale: input.rationale,
            result: input.result,
            artifacts: input.artifacts,
            evidence: input.evidence,
            extraction: input.extraction,
            created_at: input.created_at,
        })
    }

    pub fn id(&self) -> &HypothesisId {
        &self.hypothesis_id
    }

    pub fn memory_space_id(&self) -> &MemorySpaceId {
        &self.memory_space_id
    }

    pub fn content_digest(&self) -> &Sha256Digest {
        &self.content_digest
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

    pub fn result(&self) -> &str {
        &self.result
    }

    pub fn artifacts(&self) -> &[String] {
        &self.artifacts
    }

    pub fn evidence(&self) -> &HypothesisEvidence {
        &self.evidence
    }

    pub fn extraction(&self) -> &HypothesisExtraction {
        &self.extraction
    }

    pub fn created_at(&self) -> OffsetDateTime {
        self.created_at
    }
}

pub type HypothesisPayload = Hypothesis;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct HypothesisEvidenceWire {
    source_system: String,
    source_instance_id: String,
    source_profile_id: String,
    source_session_id: String,
    source_round_id: String,
    raw_round_digest: Sha256Digest,
    normalized_round_digest: Sha256Digest,
    source_event_ids: Vec<ProjectionEventId>,
}

impl TryFrom<HypothesisEvidenceWire> for HypothesisEvidence {
    type Error = DomainError;

    fn try_from(value: HypothesisEvidenceWire) -> Result<Self, Self::Error> {
        Self::new(
            value.source_system,
            value.source_instance_id,
            value.source_profile_id,
            value.source_session_id,
            value.source_round_id,
            value.raw_round_digest,
            value.normalized_round_digest,
            value.source_event_ids,
        )
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct HypothesisExtractionWire {
    provider: String,
    model: String,
    prompt_version: u32,
    schema_version: u32,
    completed_at: OffsetDateTime,
}

impl TryFrom<HypothesisExtractionWire> for HypothesisExtraction {
    type Error = DomainError;

    fn try_from(value: HypothesisExtractionWire) -> Result<Self, Self::Error> {
        Self::new(
            value.provider,
            value.model,
            value.prompt_version,
            value.schema_version,
            value.completed_at,
        )
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct HypothesisWire {
    hypothesis_id: HypothesisId,
    memory_space_id: MemorySpaceId,
    content_digest: Sha256Digest,
    title: String,
    target: String,
    statement: String,
    rationale: String,
    result: String,
    artifacts: Vec<String>,
    evidence: HypothesisEvidence,
    extraction: HypothesisExtraction,
    created_at: OffsetDateTime,
}

impl TryFrom<HypothesisWire> for Hypothesis {
    type Error = DomainError;

    fn try_from(value: HypothesisWire) -> Result<Self, Self::Error> {
        Self::new(HypothesisInput {
            hypothesis_id: value.hypothesis_id,
            memory_space_id: value.memory_space_id,
            content_digest: value.content_digest,
            title: value.title,
            target: value.target,
            statement: value.statement,
            rationale: value.rationale,
            result: value.result,
            artifacts: value.artifacts,
            evidence: value.evidence,
            extraction: value.extraction,
            created_at: value.created_at,
        })
    }
}
