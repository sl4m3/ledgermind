use ledgermind_storage_sqlite::{Database, StorageError};
use rusqlite::params;

#[test]
fn fresh_database_applies_schema_and_records_migration() {
    let mut database = Database::open_in_memory().expect("database opens");

    database.migrate().expect("migration succeeds");

    let connection = database.connection();
    let migration_count: i64 = connection
        .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
            row.get(0)
        })
        .expect("migration row exists");
    assert_eq!(migration_count, 4);

    for table in [
        "memory_spaces",
        "hypotheses",
        "knowledge_items",
        "knowledge_revisions",
        "evidence_links",
        "supersession_links",
        "idempotency_results",
        "model_tasks",
        "context_usage",
        "projection_events",
        "knowledge_items_fts",
    ] {
        let exists: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?1",
                [table],
                |row| row.get(0),
            )
            .expect("table lookup succeeds");
        assert_eq!(exists, 1, "missing table {table}");
    }
}

#[test]
fn applying_migrations_twice_is_a_noop() {
    let mut database = Database::open_in_memory().expect("database opens");

    database.migrate().expect("first migration succeeds");
    database.migrate().expect("second migration succeeds");

    let migration_count: i64 = database
        .connection()
        .query_row("SELECT COUNT(*) FROM schema_migrations", [], |row| {
            row.get(0)
        })
        .expect("migration rows can be counted");
    assert_eq!(migration_count, 4);
}

#[test]
fn changing_an_applied_migration_checksum_is_rejected() {
    let mut database = Database::open_in_memory().expect("database opens");
    database.migrate().expect("migration succeeds");
    database
        .connection_mut()
        .execute(
            "UPDATE schema_migrations SET checksum = ?1 WHERE version = 1",
            params!["sha256:tampered"],
        )
        .expect("test can tamper with checksum");

    let error = database
        .migrate()
        .expect_err("tampered migration must fail");
    assert!(matches!(
        error,
        StorageError::MigrationChecksumMismatch { version: 1, .. }
    ));
}
