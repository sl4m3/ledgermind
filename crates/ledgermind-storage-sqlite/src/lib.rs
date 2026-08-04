#![forbid(unsafe_code)]

//! SQLite persistence for the closed Core. SQL is isolated to this crate.

mod database;
pub mod error;
pub mod integrity;
mod migrations;
mod repositories;
mod service;
mod uow;

pub use database::Database;
pub use error::StorageError;
pub use integrity::IntegrityReport;
pub use migrations::MigrationRunner;
pub use repositories::{
    SqliteContextUsageRepository, SqliteEvidenceRepository, SqliteHypothesisRepository,
    SqliteIdempotencyRepository, SqliteKnowledgeRepository, SqliteModelTaskRepository,
    SqliteProjectionEventRepository, SqliteRepositories, SqliteRevisionRepository,
};
pub use service::SqliteCoreService;
pub use uow::SqliteUnitOfWork;
