use thiserror::Error;

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum IdentifierError {
    #[error("{type_name} must not be empty")]
    Empty { type_name: &'static str },
    #[error("{type_name} must match sha256:<64 lowercase hex characters>")]
    InvalidSha256 { type_name: &'static str },
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum DomainError {
    #[error(transparent)]
    Identifier(#[from] IdentifierError),
    #[error("{field} must not be empty")]
    EmptyField { field: &'static str },
    #[error("{field} must be at most {maximum} characters, got {actual}")]
    FieldTooLong {
        field: &'static str,
        maximum: usize,
        actual: usize,
    },
    #[error("{field} must be at least {minimum}, got {actual}")]
    InvalidVersion {
        field: &'static str,
        minimum: u64,
        actual: u64,
    },
    #[error("{field} must be timezone-aware")]
    InvalidTimestamp { field: &'static str },
    #[error("updated_at must be greater than or equal to created_at")]
    TimestampOrder,
    #[error("an entity cannot supersede itself")]
    SelfSupersession,
    #[error("knowledge item is already superseded")]
    AlreadySuperseded,
    #[error("knowledge item is already deleted")]
    AlreadyDeleted,
    #[error("knowledge creation requires at least one origin evidence link")]
    MissingOriginEvidence,
    #[error("unknown phase: {value}")]
    UnknownPhase { value: String },
    #[error("snapshot_json must be a JSON object")]
    SnapshotMustBeObject,
    #[error("snapshot_json must be valid JSON: {reason}")]
    InvalidSnapshot { reason: String },
}

pub type DomainResult<T> = Result<T, DomainError>;
