use ledgermind_storage_sqlite::{Database, StorageError};

#[test]
fn fresh_core_database_passes_integrity_and_ownership_checks() {
    let mut database = Database::open_in_memory().expect("database opens");
    database.migrate().expect("database migrates");

    let report = database
        .verify_integrity()
        .expect("integrity query succeeds");
    assert!(report.sqlite_integrity_ok);
    assert_eq!(report.foreign_key_violations, 0);
    assert!(report.unexpected_tables.is_empty());
    database
        .verify_core_schema()
        .expect("core schema ownership is valid");
}

#[test]
fn core_schema_rejects_an_unexpected_local_owned_table() {
    let mut database = Database::open_in_memory().expect("database opens");
    database.migrate().expect("database migrates");
    database
        .connection_mut()
        .execute_batch("CREATE TABLE rounds (round_id TEXT PRIMARY KEY)")
        .expect("unexpected table creates");

    let report = database
        .verify_integrity()
        .expect("integrity query succeeds");
    assert_eq!(report.unexpected_tables, vec!["rounds".to_owned()]);
    let error = database
        .verify_core_schema()
        .expect_err("ownership check must fail");
    assert!(matches!(error, StorageError::Integrity(message) if message.contains("rounds")));
}

#[cfg(unix)]
#[test]
fn file_database_is_created_with_private_permissions() {
    use std::{os::unix::fs::PermissionsExt, path::PathBuf};

    let directory = tempfile::tempdir().expect("temp directory creates");
    let path: PathBuf = directory.path().join("knowledge.db");
    let database = Database::open(&path).expect("file database opens");
    drop(database);

    let mode = std::fs::metadata(path)
        .expect("database metadata reads")
        .permissions()
        .mode()
        & 0o777;
    assert_eq!(mode, 0o600);
}

#[cfg(unix)]
#[test]
fn missing_core_data_directory_is_created_with_private_permissions() {
    use std::{os::unix::fs::PermissionsExt, path::PathBuf};

    let directory = tempfile::tempdir().expect("temp directory creates");
    let core_directory = directory.path().join("core-data");
    let path: PathBuf = core_directory.join("knowledge.db");
    let database = Database::open(&path).expect("nested file database opens");
    drop(database);

    let directory_mode = std::fs::metadata(&core_directory)
        .expect("core directory metadata reads")
        .permissions()
        .mode()
        & 0o777;
    let database_mode = std::fs::metadata(path)
        .expect("database metadata reads")
        .permissions()
        .mode()
        & 0o777;
    assert_eq!(directory_mode, 0o700);
    assert_eq!(database_mode, 0o600);
}
