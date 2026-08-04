use ledgermind_domain::{
    Hypothesis, IdempotencyKey, KnowledgeId, MemorySpaceId, ModelTaskId, ProjectionEventId,
    Sha256Digest,
};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;

use crate::{KnowledgeSearchHit, RepositoryError};
use crate::{ModelTaskRecord, ModelTaskSubmission};

#[derive(Clone, Debug)]
pub struct AcceptHypothesisCommand {
    pub command_id: String,
    pub idempotency_key: IdempotencyKey,
    pub request_hash: Sha256Digest,
    pub memory_space_id: MemorySpaceId,
    pub hypothesis: Hypothesis,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AcceptHypothesisResult {
    pub accepted: bool,
    pub duplicate: bool,
    pub core_reference_id: Option<KnowledgeId>,
    pub result_json: Option<String>,
}

#[derive(Clone, Debug)]
pub struct RetrieveContextRequest {
    pub memory_space_id: MemorySpaceId,
    pub query: String,
    pub limit: u32,
    pub candidate_ids: Vec<KnowledgeId>,
    pub candidate_scores: Vec<(KnowledgeId, f64)>,
}

#[derive(Clone, Debug, Default)]
pub struct ContextView {
    pub items: Vec<KnowledgeSearchHit>,
}

#[derive(Clone, Debug)]
pub struct RecordContextUsageCommand {
    pub usage_id: String,
    pub memory_space_id: MemorySpaceId,
    pub item_ids: Vec<KnowledgeId>,
    pub used_at: OffsetDateTime,
    pub session_id: Option<String>,
    pub round_id: Option<String>,
}

#[derive(Clone, Debug)]
pub struct PollProjectionEventsRequest {
    pub memory_space_id: MemorySpaceId,
    pub consumer_id: String,
    pub after_event_id: Option<ProjectionEventId>,
    pub limit: u32,
}

#[derive(Clone, Debug)]
pub struct ProjectionEventPage {
    pub events: Vec<crate::ProjectionEventRecord>,
    pub has_more: bool,
}

#[derive(Clone, Debug)]
pub struct AckProjectionEventsCommand {
    pub consumer_id: String,
    pub event_ids: Vec<ProjectionEventId>,
}

#[derive(Clone, Debug)]
pub struct PollModelTasksRequest {
    pub memory_space_id: MemorySpaceId,
    pub worker_id: String,
    pub limit: u32,
    pub lease_seconds: u64,
}

#[derive(Clone, Debug)]
pub struct ModelTaskPage {
    pub tasks: Vec<ModelTaskRecord>,
    pub has_more: bool,
}

#[derive(Clone, Debug)]
pub struct SubmitModelResultCommand {
    pub task_id: ModelTaskId,
    pub memory_space_id: MemorySpaceId,
    pub worker_id: String,
    pub result_json: String,
}

pub type SubmitModelResult = ModelTaskSubmission;

pub trait CoreService {
    type Error: RepositoryError;

    fn accept_hypothesis(
        &mut self,
        command: &AcceptHypothesisCommand,
    ) -> Result<AcceptHypothesisResult, Self::Error>;

    fn retrieve_context(
        &self,
        request: &RetrieveContextRequest,
    ) -> Result<ContextView, Self::Error>;

    fn record_context_usage(
        &mut self,
        command: &RecordContextUsageCommand,
    ) -> Result<(), Self::Error>;

    fn poll_projection_events(
        &self,
        request: &PollProjectionEventsRequest,
    ) -> Result<ProjectionEventPage, Self::Error>;

    fn ack_projection_events(
        &mut self,
        command: &AckProjectionEventsCommand,
    ) -> Result<Vec<ProjectionEventId>, Self::Error>;

    fn poll_model_tasks(
        &mut self,
        request: &PollModelTasksRequest,
    ) -> Result<ModelTaskPage, Self::Error>;

    fn submit_model_result(
        &mut self,
        command: &SubmitModelResultCommand,
    ) -> Result<SubmitModelResult, Self::Error>;
}
