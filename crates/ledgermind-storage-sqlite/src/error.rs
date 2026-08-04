use thiserror::Error;

use ledgermind_domain::DomainError;

#[derive(Debug, Error)]
pub enum StorageError {
    #[error("filesystem error: {0}")]
    Io(#[from] std::io::Error),

    #[error("sqlite error: {0}")]
    Sqlite(#[from] rusqlite::Error),

    #[error("migration {version} checksum mismatch: expected {expected}, found {actual}")]
    MigrationChecksumMismatch {
        version: u32,
        expected: String,
        actual: String,
    },

    #[error("migration {version} name mismatch: expected {expected}, found {actual}")]
    MigrationNameMismatch {
        version: u32,
        expected: String,
        actual: String,
    },

    #[error("database contains unknown applied migration version {version}")]
    UnknownAppliedMigration { version: u32 },

    #[error("database migration state is missing version {version} before a later migration")]
    MissingAppliedMigration { version: u32 },

    #[error("timestamp encoding failed: {0}")]
    Timestamp(String),

    #[error("JSON encoding failed: {0}")]
    Json(#[from] serde_json::Error),

    #[error("domain validation failed: {0}")]
    Domain(#[from] DomainError),

    #[error("idempotency conflict for memory space {memory_space_id} and key {key}")]
    IdempotencyConflict {
        memory_space_id: String,
        key: String,
    },

    #[error(
        "optimistic version conflict for knowledge {knowledge_id}: expected {expected}, found {actual}"
    )]
    VersionConflict {
        knowledge_id: String,
        expected: u64,
        actual: u64,
    },

    #[error("record not found: {0}")]
    NotFound(String),

    #[error("stale model task: {0}")]
    StaleModelTask(String),

    #[error("invalid stored record: {0}")]
    InvalidRecord(String),

    #[error("transaction error: {0}")]
    Transaction(String),

    #[error("integrity violation: {0}")]
    Integrity(String),
}
