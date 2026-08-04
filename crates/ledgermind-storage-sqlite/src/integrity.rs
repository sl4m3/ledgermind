use rusqlite::Connection;

use crate::StorageError;

const CORE_TABLES: &[&str] = &[
    "context_usage",
    "evidence_links",
    "hypotheses",
    "idempotency_results",
    "knowledge_items",
    "knowledge_items_fts",
    "knowledge_revisions",
    "memory_spaces",
    "model_tasks",
    "projection_event_acknowledgements",
    "projection_events",
    "schema_migrations",
    "supersession_links",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IntegrityReport {
    pub sqlite_integrity_ok: bool,
    pub foreign_key_violations: u64,
    pub unexpected_tables: Vec<String>,
}

pub fn verify_integrity(connection: &Connection) -> Result<IntegrityReport, StorageError> {
    let sqlite_result: String =
        connection.query_row("PRAGMA integrity_check", [], |row| row.get(0))?;
    let mut foreign_key_rows = connection.prepare("PRAGMA foreign_key_check")?;
    let foreign_key_violations = foreign_key_rows.query_map([], |_| Ok(()))?.count();
    let foreign_key_violations = u64::try_from(foreign_key_violations)
        .map_err(|_| StorageError::InvalidRecord("foreign key count overflow".to_owned()))?;

    let mut tables_statement = connection.prepare(
        "SELECT name FROM sqlite_master
         WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
         ORDER BY name",
    )?;
    let tables = tables_statement.query_map([], |row| row.get::<_, String>(0))?;
    let tables: Vec<String> = tables.collect::<Result<_, _>>()?;
    let unexpected_tables = tables
        .iter()
        .filter(|table| {
            !CORE_TABLES.contains(&table.as_str()) && !table.starts_with("knowledge_items_fts_")
        })
        .cloned()
        .collect();

    Ok(IntegrityReport {
        sqlite_integrity_ok: sqlite_result.eq_ignore_ascii_case("ok"),
        foreign_key_violations,
        unexpected_tables,
    })
}

pub fn verify_core_schema(connection: &Connection) -> Result<(), StorageError> {
    let report = verify_integrity(connection)?;
    if !report.sqlite_integrity_ok {
        return Err(StorageError::Integrity(
            "SQLite integrity_check did not return ok".to_owned(),
        ));
    }
    if report.foreign_key_violations != 0 {
        return Err(StorageError::Integrity(format!(
            "SQLite foreign_key_check returned {} violations",
            report.foreign_key_violations
        )));
    }
    if !report.unexpected_tables.is_empty() {
        return Err(StorageError::Integrity(format!(
            "unexpected non-Core tables: {}",
            report.unexpected_tables.join(", ")
        )));
    }

    let missing_tables = CORE_TABLES
        .iter()
        .filter(|table| {
            connection
                .query_row(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?1",
                    [table],
                    |_| Ok(()),
                )
                .is_err()
        })
        .copied()
        .collect::<Vec<_>>();
    if !missing_tables.is_empty() {
        return Err(StorageError::Integrity(format!(
            "missing Core tables: {}",
            missing_tables.join(", ")
        )));
    }

    let dangling_current_revisions: i64 = connection.query_row(
        "SELECT COUNT(*)
         FROM knowledge_items k
         LEFT JOIN knowledge_revisions r ON r.revision_id = k.current_revision_id
         WHERE k.current_revision_id IS NOT NULL AND r.revision_id IS NULL",
        [],
        |row| row.get(0),
    )?;
    if dangling_current_revisions != 0 {
        return Err(StorageError::Integrity(format!(
            "{dangling_current_revisions} knowledge items have dangling current revisions"
        )));
    }
    Ok(())
}
