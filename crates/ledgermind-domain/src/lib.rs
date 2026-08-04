#![forbid(unsafe_code)]

//! Closed Core domain model. Transport and persistence stay outside this crate.

pub mod errors;
pub mod evidence;
pub mod hypothesis;
pub mod identifiers;
pub mod knowledge;
pub mod merge;
pub mod phase;
pub mod revision;

pub use errors::{DomainError, DomainResult, IdentifierError};
pub use evidence::{EvidenceLink, EvidenceRelation, KnowledgeEvidence, assert_has_origin_relation};
pub use hypothesis::{
    Hypothesis, HypothesisEvidence, HypothesisExtraction, HypothesisInput, HypothesisPayload,
};
pub use identifiers::{
    HypothesisId, IdempotencyKey, KnowledgeId, MemorySpaceId, ModelTaskId, ProjectionEventId,
    RevisionId, Sha256Digest,
};
pub use knowledge::{KnowledgeInput, KnowledgeItem};
pub use merge::{MergeProposal, MergeProposalInput};
pub use phase::Phase;
pub use revision::KnowledgeRevision;
