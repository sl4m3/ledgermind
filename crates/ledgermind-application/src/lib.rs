#![forbid(unsafe_code)]

//! Core application ports and use cases.

mod commands;
pub mod ports;

pub use commands::{
    AcceptHypothesisCommand, AcceptHypothesisResult, AckProjectionEventsCommand, ContextView,
    CoreService, ModelTaskPage, PollModelTasksRequest, PollProjectionEventsRequest,
    ProjectionEventPage, RecordContextUsageCommand, RetrieveContextRequest, SubmitModelResult,
    SubmitModelResultCommand,
};
pub use ports::{
    ContextUsageRecord, ContextUsageRepository, EvidenceRepository, HypothesisRepository,
    IdempotencyRepository, KnowledgeRepository, KnowledgeSearch, KnowledgeSearchHit,
    ModelTaskRecord, ModelTaskRepository, ModelTaskSubmission, ProjectionEventRecord,
    ProjectionEventRepository, RepositoryError, RevisionRepository, StoredIdempotencyResult,
    UnitOfWork,
};
