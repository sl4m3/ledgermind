use std::collections::{BTreeMap, HashSet};

use thiserror::Error;

use ledgermind_domain::{
    Hypothesis, HypothesisEvidence, HypothesisExtraction, HypothesisId, HypothesisInput,
    IdempotencyKey, KnowledgeId, MemorySpaceId, ProjectionEventId, Sha256Digest,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};

pub const CORE_IPC_PROTOCOL_VERSION: u32 = 1;

#[derive(Debug, Error)]
pub enum ProtocolError {
    #[error("invalid protocol payload: {0}")]
    Invalid(String),

    #[error("invalid JSON: {0}")]
    Json(#[from] serde_json::Error),

    #[error("domain conversion failed: {0}")]
    Domain(#[from] ledgermind_domain::DomainError),

    #[error("invalid identifier: {0}")]
    Identifier(#[from] ledgermind_domain::IdentifierError),

    #[error("unsupported protocol version: {0}")]
    UnsupportedVersion(u32),
}

fn required(value: &str, field: &str) -> Result<(), ProtocolError> {
    if value.trim().is_empty() {
        return Err(ProtocolError::Invalid(format!("{field} must not be empty")));
    }
    Ok(())
}

fn validate_object(value: &Value, field: &str) -> Result<(), ProtocolError> {
    if !value.is_object() {
        return Err(ProtocolError::Invalid(format!("{field} must be an object")));
    }
    Ok(())
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Operation {
    Handshake,
    Health,
    AcceptHypothesis,
    RetrieveContext,
    RecordContextUsage,
    PollProjectionEvents,
    AckProjectionEvents,
    PollModelTasks,
    SubmitModelResult,
    Shutdown,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CoreErrorCode {
    InvalidRequest,
    InvalidHypothesis,
    IdempotencyConflict,
    MemorySpaceMismatch,
    NotFound,
    VersionConflict,
    StaleModelTask,
    IntegrityViolation,
    ProtocolVersionUnsupported,
    StorageUnavailable,
    InternalError,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CoreError {
    pub code: CoreErrorCode,
    pub message: String,
    pub error_id: String,
    pub retryable: bool,
}

impl CoreError {
    pub fn new(
        code: CoreErrorCode,
        message: impl Into<String>,
        error_id: impl Into<String>,
        retryable: bool,
    ) -> Result<Self, ProtocolError> {
        let message = message.into();
        let error_id = error_id.into();
        required(&message, "error message")?;
        required(&error_id, "error id")?;
        Ok(Self {
            code,
            message,
            error_id,
            retryable,
        })
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CoreRequestEnvelope {
    pub protocol_version: u32,
    pub request_id: String,
    pub operation: Operation,
    pub payload: Value,
}

impl CoreRequestEnvelope {
    pub fn new(
        request_id: impl Into<String>,
        operation: Operation,
        payload: Value,
    ) -> Result<Self, ProtocolError> {
        let envelope = Self {
            protocol_version: CORE_IPC_PROTOCOL_VERSION,
            request_id: request_id.into(),
            operation,
            payload,
        };
        envelope.validate()?;
        Ok(envelope)
    }

    pub fn validate(&self) -> Result<(), ProtocolError> {
        if self.protocol_version != CORE_IPC_PROTOCOL_VERSION {
            return Err(ProtocolError::UnsupportedVersion(self.protocol_version));
        }
        required(&self.request_id, "request id")?;
        validate_object(&self.payload, "request payload")
    }

    pub fn from_json(payload: &str) -> Result<Self, ProtocolError> {
        let envelope: Self = serde_json::from_str(payload)?;
        envelope.validate()?;
        Ok(envelope)
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("CoreRequestEnvelope serialization is infallible")
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum ResponseStatus {
    Ok,
    Error,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CoreResponseEnvelope {
    pub protocol_version: u32,
    pub request_id: String,
    pub status: ResponseStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<CoreError>,
}

impl CoreResponseEnvelope {
    pub fn ok(request_id: impl Into<String>, result: Value) -> Result<Self, ProtocolError> {
        validate_object(&result, "response result")?;
        let envelope = Self {
            protocol_version: CORE_IPC_PROTOCOL_VERSION,
            request_id: request_id.into(),
            status: ResponseStatus::Ok,
            result: Some(result),
            error: None,
        };
        envelope.validate()?;
        Ok(envelope)
    }

    pub fn error(request_id: impl Into<String>, error: CoreError) -> Result<Self, ProtocolError> {
        let envelope = Self {
            protocol_version: CORE_IPC_PROTOCOL_VERSION,
            request_id: request_id.into(),
            status: ResponseStatus::Error,
            result: None,
            error: Some(error),
        };
        envelope.validate()?;
        Ok(envelope)
    }

    pub fn validate(&self) -> Result<(), ProtocolError> {
        if self.protocol_version != CORE_IPC_PROTOCOL_VERSION {
            return Err(ProtocolError::UnsupportedVersion(self.protocol_version));
        }
        required(&self.request_id, "request id")?;
        match self.status {
            ResponseStatus::Ok => {
                let Some(result) = self.result.as_ref() else {
                    return Err(ProtocolError::Invalid(
                        "successful response requires result".to_owned(),
                    ));
                };
                validate_object(result, "response result")?;
                if self.error.is_some() {
                    return Err(ProtocolError::Invalid(
                        "successful response cannot contain error".to_owned(),
                    ));
                }
            }
            ResponseStatus::Error => {
                if self.result.is_some() || self.error.is_none() {
                    return Err(ProtocolError::Invalid(
                        "error response requires error and no result".to_owned(),
                    ));
                }
            }
        }
        Ok(())
    }

    pub fn from_json(payload: &str) -> Result<Self, ProtocolError> {
        let envelope: Self = serde_json::from_str(payload)?;
        envelope.validate()?;
        Ok(envelope)
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("CoreResponseEnvelope serialization is infallible")
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HandshakePayload {
    pub client_name: String,
    pub client_version: String,
    pub supported_operations: Vec<Operation>,
    #[serde(default)]
    pub capabilities: serde_json::Map<String, Value>,
}

impl HandshakePayload {
    pub fn validate(&self) -> Result<(), ProtocolError> {
        required(&self.client_name, "client name")?;
        required(&self.client_version, "client version")?;
        if self.supported_operations.is_empty() {
            return Err(ProtocolError::Invalid(
                "supported operations must not be empty".to_owned(),
            ));
        }
        if self
            .supported_operations
            .iter()
            .enumerate()
            .any(|(index, operation)| self.supported_operations[..index].contains(operation))
        {
            return Err(ProtocolError::Invalid(
                "supported operations must be unique".to_owned(),
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HypothesisEvidencePayload {
    pub source_system: String,
    pub source_instance_id: String,
    pub source_profile_id: String,
    pub source_session_id: String,
    pub source_round_id: String,
    pub raw_round_digest: String,
    pub normalized_round_digest: String,
    pub source_event_ids: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HypothesisExtractionPayload {
    pub provider: String,
    pub model: String,
    pub prompt_version: u32,
    pub schema_version: u32,
    pub completed_at: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HypothesisPayload {
    pub hypothesis_id: String,
    pub content_digest: String,
    pub title: String,
    pub target: String,
    pub statement: String,
    #[serde(default)]
    pub rationale: String,
    #[serde(default)]
    pub result: String,
    #[serde(default)]
    pub artifacts: Vec<String>,
    pub evidence: HypothesisEvidencePayload,
    pub extraction: HypothesisExtractionPayload,
}

#[derive(Clone, Debug)]
pub struct AcceptHypothesisDomainInput {
    pub command_id: String,
    pub idempotency_key: IdempotencyKey,
    pub request_hash: Sha256Digest,
    pub memory_space_id: MemorySpaceId,
    pub hypothesis: Hypothesis,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AcceptHypothesisPayload {
    pub protocol_version: u32,
    pub command_id: String,
    pub idempotency_key: String,
    pub memory_space_id: String,
    pub hypothesis: HypothesisPayload,
}

impl AcceptHypothesisPayload {
    pub fn into_domain(self) -> Result<AcceptHypothesisDomainInput, ProtocolError> {
        if self.protocol_version != CORE_IPC_PROTOCOL_VERSION {
            return Err(ProtocolError::UnsupportedVersion(self.protocol_version));
        }
        let request_hash = Sha256Digest::from_bytes(&serde_json::to_vec(&self)?);
        required(&self.command_id, "command id")?;
        let memory_space_id = MemorySpaceId::try_from(self.memory_space_id)?;
        let idempotency_key = IdempotencyKey::try_from(self.idempotency_key)?;
        let hypothesis_id = HypothesisId::try_from(self.hypothesis.hypothesis_id)?;
        let content_digest = Sha256Digest::try_from(self.hypothesis.content_digest)?;
        let source_event_ids = self
            .hypothesis
            .evidence
            .source_event_ids
            .into_iter()
            .map(ProjectionEventId::try_from)
            .collect::<Result<Vec<_>, _>>()?;
        let evidence = HypothesisEvidence::new(
            self.hypothesis.evidence.source_system,
            self.hypothesis.evidence.source_instance_id,
            self.hypothesis.evidence.source_profile_id,
            self.hypothesis.evidence.source_session_id,
            self.hypothesis.evidence.source_round_id,
            Sha256Digest::try_from(self.hypothesis.evidence.raw_round_digest)?,
            Sha256Digest::try_from(self.hypothesis.evidence.normalized_round_digest)?,
            source_event_ids,
        )?;
        let completed_at =
            OffsetDateTime::parse(&self.hypothesis.extraction.completed_at, &Rfc3339)
                .map_err(|error| ProtocolError::Invalid(format!("completed_at: {error}")))?;
        let extraction = HypothesisExtraction::new(
            self.hypothesis.extraction.provider,
            self.hypothesis.extraction.model,
            self.hypothesis.extraction.prompt_version,
            self.hypothesis.extraction.schema_version,
            completed_at,
        )?;
        let hypothesis = Hypothesis::new(HypothesisInput {
            hypothesis_id,
            memory_space_id: memory_space_id.clone(),
            content_digest,
            title: self.hypothesis.title,
            target: self.hypothesis.target,
            statement: self.hypothesis.statement,
            rationale: self.hypothesis.rationale,
            result: self.hypothesis.result,
            artifacts: self.hypothesis.artifacts,
            evidence,
            extraction,
            created_at: completed_at,
        })?;
        if hypothesis.memory_space_id() != &memory_space_id {
            return Err(ProtocolError::Invalid(
                "hypothesis memory space does not match command".to_owned(),
            ));
        }
        Ok(AcceptHypothesisDomainInput {
            command_id: self.command_id,
            idempotency_key,
            request_hash,
            memory_space_id,
            hypothesis,
        })
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateScorePayload {
    pub knowledge_id: String,
    pub score: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RetrieveContextPayload {
    pub memory_space_id: String,
    pub query: String,
    pub limit: u32,
    #[serde(default)]
    pub candidate_ids: Vec<String>,
    #[serde(default)]
    pub candidate_scores: Vec<CandidateScorePayload>,
}

#[derive(Clone, Debug)]
pub struct RetrieveContextInput {
    pub memory_space_id: MemorySpaceId,
    pub query: String,
    pub limit: u32,
    pub candidate_ids: Vec<KnowledgeId>,
    pub candidate_scores: Vec<(KnowledgeId, f64)>,
}

impl RetrieveContextPayload {
    pub fn into_domain(self) -> Result<RetrieveContextInput, ProtocolError> {
        required(&self.query, "query")?;
        if !(1..=100).contains(&self.limit) {
            return Err(ProtocolError::Invalid(
                "limit must be between 1 and 100".to_owned(),
            ));
        }
        let candidate_ids = self
            .candidate_ids
            .into_iter()
            .map(KnowledgeId::try_from)
            .collect::<Result<Vec<_>, _>>()?;
        let mut seen_ids = HashSet::new();
        if candidate_ids
            .iter()
            .any(|candidate_id| !seen_ids.insert(candidate_id.as_str()))
        {
            return Err(ProtocolError::Invalid(
                "candidate_ids must be unique".to_owned(),
            ));
        }
        let candidate_scores = self
            .candidate_scores
            .into_iter()
            .map(|candidate| {
                if !candidate.score.is_finite() || !(0.0..=1.0).contains(&candidate.score) {
                    return Err(ProtocolError::Invalid(
                        "candidate score must be between 0 and 1".to_owned(),
                    ));
                }
                let knowledge_id = KnowledgeId::try_from(candidate.knowledge_id)?;
                if !candidate_ids.iter().any(|id| id == &knowledge_id) {
                    return Err(ProtocolError::Invalid(
                        "candidate score must refer to candidate_ids".to_owned(),
                    ));
                }
                Ok((knowledge_id, candidate.score))
            })
            .collect::<Result<Vec<_>, ProtocolError>>()?;
        let mut seen_scores = HashSet::new();
        if candidate_scores
            .iter()
            .any(|(candidate_id, _)| !seen_scores.insert(candidate_id.as_str()))
        {
            return Err(ProtocolError::Invalid(
                "candidate_scores IDs must be unique".to_owned(),
            ));
        }
        Ok(RetrieveContextInput {
            memory_space_id: MemorySpaceId::try_from(self.memory_space_id)?,
            query: self.query,
            limit: self.limit,
            candidate_ids,
            candidate_scores,
        })
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RecordContextUsagePayload {
    pub memory_space_id: String,
    pub item_ids: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct RecordContextUsageInput {
    pub memory_space_id: MemorySpaceId,
    pub item_ids: Vec<KnowledgeId>,
}

impl RecordContextUsagePayload {
    pub fn into_domain(self) -> Result<RecordContextUsageInput, ProtocolError> {
        let mut seen = HashSet::new();
        if self
            .item_ids
            .iter()
            .any(|item_id| !seen.insert(item_id.as_str()))
        {
            return Err(ProtocolError::Invalid("item_ids must be unique".to_owned()));
        }
        Ok(RecordContextUsageInput {
            memory_space_id: MemorySpaceId::try_from(self.memory_space_id)?,
            item_ids: self
                .item_ids
                .into_iter()
                .map(KnowledgeId::try_from)
                .collect::<Result<Vec<_>, _>>()?,
        })
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HealthResult {
    pub healthy: bool,
    pub backend: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
    pub protocol_version: u32,
    pub schema_version: u32,
    pub environment_keys: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContextViewItemPayload {
    pub knowledge_id: String,
    pub title: String,
    pub target: String,
    pub statement: String,
    pub relevance: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContextViewPayload {
    pub api_version: String,
    pub items: Vec<ContextViewItemPayload>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AcceptHypothesisResultPayload {
    pub accepted: bool,
    pub duplicate: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub core_reference_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result_json: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RecordContextUsageResultPayload {
    pub recorded: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectionUpsertPayload {
    pub knowledge_id: String,
    pub memory_space_id: String,
    pub title: String,
    pub target: String,
    pub statement: String,
    pub projection_version: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectionDeletePayload {
    pub knowledge_id: String,
    pub memory_space_id: String,
    pub projection_version: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectionEventPayload {
    pub event_id: String,
    pub memory_space_id: String,
    pub aggregate_id: String,
    pub event_type: String,
    pub payload: Value,
    pub occurred_at: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PollProjectionEventsPayload {
    pub memory_space_id: String,
    pub consumer_id: String,
    pub after_event_id: Option<String>,
    pub limit: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PollProjectionEventsResultPayload {
    pub events: Vec<ProjectionEventPayload>,
    pub has_more: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AckProjectionEventsPayload {
    pub consumer_id: String,
    pub event_ids: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AckProjectionEventsResultPayload {
    pub acknowledged: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelTaskPayload {
    pub task_id: String,
    pub operation: String,
    pub memory_space_id: String,
    pub expected_versions: BTreeMap<String, u64>,
    pub expires_at: String,
    pub model_input: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lease_expires_at: Option<String>,
}

impl ModelTaskPayload {
    pub fn validate(&self) -> Result<(), ProtocolError> {
        required(&self.task_id, "task id")?;
        required(&self.memory_space_id, "memory space id")?;
        if self.operation != "merge_knowledge" {
            return Err(ProtocolError::Invalid(
                "unsupported model task operation".to_owned(),
            ));
        }
        if self.expected_versions.len() < 2 {
            return Err(ProtocolError::Invalid(
                "merge task requires at least two expected versions".to_owned(),
            ));
        }
        OffsetDateTime::parse(&self.expires_at, &Rfc3339)
            .map_err(|error| ProtocolError::Invalid(format!("expires_at: {error}")))?;
        if let Some(lease_expires_at) = &self.lease_expires_at {
            OffsetDateTime::parse(lease_expires_at, &Rfc3339)
                .map_err(|error| ProtocolError::Invalid(format!("lease_expires_at: {error}")))?;
        }
        validate_object(&self.model_input, "model_input")
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PollModelTasksPayload {
    pub memory_space_id: String,
    pub worker_id: String,
    pub limit: u32,
    pub lease_seconds: u64,
}

impl PollModelTasksPayload {
    pub fn validate(&self) -> Result<(), ProtocolError> {
        required(&self.memory_space_id, "memory space id")?;
        required(&self.worker_id, "worker id")?;
        if !(1..=100).contains(&self.limit) {
            return Err(ProtocolError::Invalid(
                "limit must be between 1 and 100".to_owned(),
            ));
        }
        if !(1..=3600).contains(&self.lease_seconds) {
            return Err(ProtocolError::Invalid(
                "lease_seconds must be between 1 and 3600".to_owned(),
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PollModelTasksResultPayload {
    pub tasks: Vec<ModelTaskPayload>,
    pub has_more: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SubmitModelResultPayload {
    pub task_id: String,
    pub memory_space_id: String,
    pub worker_id: String,
    pub result: Value,
}

impl SubmitModelResultPayload {
    pub fn validate(&self) -> Result<(), ProtocolError> {
        required(&self.task_id, "task id")?;
        required(&self.memory_space_id, "memory space id")?;
        required(&self.worker_id, "worker id")?;
        validate_object(&self.result, "model result")
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SubmitModelResultResultPayload {
    pub accepted: bool,
    pub duplicate: bool,
    pub status: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ShutdownResultPayload {
    pub stopped: bool,
}
