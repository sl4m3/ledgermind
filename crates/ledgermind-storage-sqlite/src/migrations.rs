use rusqlite::{Connection, TransactionBehavior, params};
use time::{OffsetDateTime, format_description::well_known::Rfc3339};

use ledgermind_domain::Sha256Digest;

use crate::StorageError;

#[derive(Clone, Copy, Debug)]
pub struct Migration {
    pub version: u32,
    pub name: &'static str,
    pub sql: &'static str,
}

const MIGRATIONS: &[Migration] = &[
    Migration {
        version: 1,
        name: "0001_initial.sql",
        sql: include_str!("../migrations/0001_initial.sql"),
    },
    Migration {
        version: 2,
        name: "0002_knowledge_items_fts.sql",
        sql: include_str!("../migrations/0002_knowledge_items_fts.sql"),
    },
    Migration {
        version: 3,
        name: "0003_projection_event_ack.sql",
        sql: include_str!("../migrations/0003_projection_event_ack.sql"),
    },
    Migration {
        version: 4,
        name: "0004_model_task_leases.sql",
        sql: include_str!("../migrations/0004_model_task_leases.sql"),
    },
];

#[derive(Clone, Copy, Debug, Default)]
pub struct MigrationRunner;

impl MigrationRunner {
    pub const fn new() -> Self {
        Self
    }

    pub fn apply(&self, connection: &mut Connection) -> Result<(), StorageError> {
        connection.execute_batch(
            "CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )",
        )?;

        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let applied = {
            let mut statement = transaction.prepare(
                "SELECT version, name, checksum
                 FROM schema_migrations
                 ORDER BY version",
            )?;
            statement
                .query_map([], |row| {
                    Ok((
                        row.get::<_, u32>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                    ))
                })?
                .collect::<Result<Vec<_>, rusqlite::Error>>()?
        };

        for (version, name, checksum) in &applied {
            let migration = MIGRATIONS
                .iter()
                .find(|migration| migration.version == *version)
                .ok_or(StorageError::UnknownAppliedMigration { version: *version })?;
            if migration.name != name {
                return Err(StorageError::MigrationNameMismatch {
                    version: *version,
                    expected: migration.name.to_owned(),
                    actual: name.clone(),
                });
            }
            let expected = migration_checksum(migration);
            if expected != *checksum {
                return Err(StorageError::MigrationChecksumMismatch {
                    version: *version,
                    expected,
                    actual: checksum.clone(),
                });
            }
        }

        let highest_applied = applied.iter().map(|(version, _, _)| *version).max();
        if let Some(highest_applied) = highest_applied {
            for version in 1..highest_applied {
                if !applied
                    .iter()
                    .any(|(applied_version, _, _)| *applied_version == version)
                {
                    return Err(StorageError::MissingAppliedMigration { version });
                }
            }
        }

        for migration in MIGRATIONS {
            if applied
                .iter()
                .any(|(version, _, _)| *version == migration.version)
            {
                continue;
            }

            transaction.execute_batch(migration.sql)?;
            let applied_at = OffsetDateTime::now_utc()
                .format(&Rfc3339)
                .map_err(|error| StorageError::Timestamp(error.to_string()))?;
            transaction.execute(
                "INSERT INTO schema_migrations(version, name, checksum, applied_at)
                 VALUES (?1, ?2, ?3, ?4)",
                params![
                    migration.version,
                    migration.name,
                    migration_checksum(migration),
                    applied_at,
                ],
            )?;
        }

        transaction.commit()?;
        Ok(())
    }
}

fn migration_checksum(migration: &Migration) -> String {
    Sha256Digest::from_bytes(migration.sql.as_bytes()).to_string()
}
