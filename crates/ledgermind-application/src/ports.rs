use std::error::Error;

use ledgermind_domain::{
    EvidenceLink, Hypothesis, HypothesisId, IdempotencyKey, KnowledgeId, KnowledgeItem,
    KnowledgeRevision, MemorySpaceId, ModelTaskId, ProjectionEventId, RevisionId, Sha256Digest,
};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;

pub trait RepositoryError: Error + Send + Sync + 'static {}

impl<T> RepositoryError for T where T: Error + Send + Sync + 'static {}

pub trait HypothesisRepository {
    type Error: RepositoryError;

    fn add(&self, hypothesis: &Hypothesis) -> Result<(), Self::Error>;

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        hypothesis_id: &HypothesisId,
    ) -> Result<Option<Hypothesis>, Self::Error>;
}

pub trait KnowledgeRepository {
    type Error: RepositoryError;

    fn add(&self, item: &KnowledgeItem) -> Result<(), Self::Error>;

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        knowledge_id: &KnowledgeId,
    ) -> Result<Option<KnowledgeItem>, Self::Error>;

    fn update(&self, item: &KnowledgeItem, expected_version: u64) -> Result<(), Self::Error>;
}

pub trait RevisionRepository {
    type Error: RepositoryError;

    fn add(&self, revision: &KnowledgeRevision) -> Result<(), Self::Error>;

    fn list_for_knowledge(
        &self,
        memory_space_id: &MemorySpaceId,
        knowledge_id: &KnowledgeId,
    ) -> Result<Vec<KnowledgeRevision>, Self::Error>;

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        revision_id: &RevisionId,
    ) -> Result<Option<KnowledgeRevision>, Self::Error>;
}

pub trait EvidenceRepository {
    type Error: RepositoryError;

    fn add(&self, link: &EvidenceLink) -> Result<(), Self::Error>;

    fn count_for_knowledge(
        &self,
        memory_space_id: &MemorySpaceId,
        knowledge_id: &KnowledgeId,
    ) -> Result<u64, Self::Error>;

    fn list_for_knowledge(
        &self,
        memory_space_id: &MemorySpaceId,
        knowledge_id: &KnowledgeId,
    ) -> Result<Vec<EvidenceLink>, Self::Error>;
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StoredIdempotencyResult {
    pub memory_space_id: MemorySpaceId,
    pub idempotency_key: IdempotencyKey,
    pub request_hash: Sha256Digest,
    pub response_json: String,
    pub created_at: OffsetDateTime,
    pub expires_at: Option<OffsetDateTime>,
}

pub trait IdempotencyRepository {
    type Error: RepositoryError;

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        idempotency_key: &IdempotencyKey,
    ) -> Result<Option<StoredIdempotencyResult>, Self::Error>;

    fn put(&self, result: &StoredIdempotencyResult) -> Result<(), Self::Error>;
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelTaskRecord {
    pub task_id: ModelTaskId,
    pub memory_space_id: MemorySpaceId,
    pub task_type: String,
    pub status: String,
    pub request_digest: Sha256Digest,
    pub payload_json: String,
    pub result_json: Option<String>,
    pub created_at: OffsetDateTime,
    pub updated_at: OffsetDateTime,
    pub expires_at: Option<OffsetDateTime>,
    pub lease_owner: Option<String>,
    pub lease_expires_at: Option<OffsetDateTime>,
    pub attempts: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelTaskSubmission {
    pub accepted: bool,
    pub duplicate: bool,
    pub status: String,
}

pub trait ModelTaskRepository {
    type Error: RepositoryError;

    fn add(&self, task: &ModelTaskRecord) -> Result<(), Self::Error>;

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        task_id: &ModelTaskId,
    ) -> Result<Option<ModelTaskRecord>, Self::Error>;

    fn update(&self, task: &ModelTaskRecord) -> Result<(), Self::Error>;

    fn claim_for_worker(
        &self,
        memory_space_id: &MemorySpaceId,
        worker_id: &str,
        now: OffsetDateTime,
        lease_duration: time::Duration,
        limit: u32,
    ) -> Result<(Vec<ModelTaskRecord>, bool), Self::Error>;

    fn submit_result(
        &self,
        memory_space_id: &MemorySpaceId,
        task_id: &ModelTaskId,
        worker_id: &str,
        result_json: String,
        now: OffsetDateTime,
    ) -> Result<ModelTaskSubmission, Self::Error>;
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectionEventRecord {
    pub projection_event_id: ProjectionEventId,
    pub memory_space_id: MemorySpaceId,
    pub aggregate_id: String,
    pub event_type: String,
    pub payload_json: String,
    pub occurred_at: OffsetDateTime,
}

pub trait ProjectionEventRepository {
    type Error: RepositoryError;

    fn add(&self, event: &ProjectionEventRecord) -> Result<(), Self::Error>;

    fn list_for_memory_space(
        &self,
        memory_space_id: &MemorySpaceId,
    ) -> Result<Vec<ProjectionEventRecord>, Self::Error>;

    fn list_for_consumer(
        &self,
        memory_space_id: &MemorySpaceId,
        consumer_id: &str,
        after_event_id: Option<&ProjectionEventId>,
        limit: u32,
    ) -> Result<(Vec<ProjectionEventRecord>, bool), Self::Error>;

    fn acknowledge(
        &self,
        consumer_id: &str,
        event_ids: &[ProjectionEventId],
    ) -> Result<Vec<ProjectionEventId>, Self::Error>;
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ContextUsageRecord {
    pub usage_id: String,
    pub memory_space_id: MemorySpaceId,
    pub knowledge_id: Option<KnowledgeId>,
    pub surface: String,
    pub metadata_json: String,
    pub used_at: OffsetDateTime,
}

pub trait ContextUsageRepository {
    type Error: RepositoryError;

    fn add(&self, usage: &ContextUsageRecord) -> Result<(), Self::Error>;

    fn list_for_memory_space(
        &self,
        memory_space_id: &MemorySpaceId,
    ) -> Result<Vec<ContextUsageRecord>, Self::Error>;
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct KnowledgeSearchHit {
    pub knowledge_id: KnowledgeId,
    pub title: String,
    pub target: String,
    pub statement: String,
    pub relevance: f64,
}

pub trait KnowledgeSearch {
    type Error: RepositoryError;

    fn search(
        &self,
        memory_space_id: &MemorySpaceId,
        query: &str,
        limit: u32,
    ) -> Result<Vec<KnowledgeSearchHit>, Self::Error>;
}

pub trait UnitOfWork {
    type Error: RepositoryError;

    fn begin_immediate(&mut self) -> Result<(), Self::Error>;

    fn commit(&mut self) -> Result<(), Self::Error>;

    fn rollback(&mut self) -> Result<(), Self::Error>;
}
