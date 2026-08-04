use std::{fs, path::Path, time::Duration};

use rusqlite::Connection;

use crate::{IntegrityReport, MigrationRunner, SqliteUnitOfWork, StorageError};

pub struct Database {
    connection: Connection,
}

impl Database {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, StorageError> {
        let path = path.as_ref();
        Self::ensure_parent_directory(path)?;
        let connection = Connection::open(path)?;
        Self::ensure_private_permissions(path)?;
        Self::from_connection(connection)
    }

    pub fn open_in_memory() -> Result<Self, StorageError> {
        Self::from_connection(Connection::open_in_memory()?)
    }

    pub fn migrate(&mut self) -> Result<(), StorageError> {
        MigrationRunner::new().apply(&mut self.connection)
    }

    pub fn connection(&self) -> &Connection {
        &self.connection
    }

    pub fn connection_mut(&mut self) -> &mut Connection {
        &mut self.connection
    }

    pub fn into_connection(self) -> Connection {
        self.connection
    }

    pub fn unit_of_work(&mut self) -> SqliteUnitOfWork<'_> {
        SqliteUnitOfWork::new(&mut self.connection)
    }

    pub fn verify_integrity(&self) -> Result<IntegrityReport, StorageError> {
        crate::integrity::verify_integrity(&self.connection)
    }

    pub fn verify_core_schema(&self) -> Result<(), StorageError> {
        crate::integrity::verify_core_schema(&self.connection)
    }

    pub fn schema_version(&self) -> Result<u32, StorageError> {
        let version =
            self.connection
                .query_row("SELECT MAX(version) FROM schema_migrations", [], |row| {
                    row.get::<_, Option<u32>>(0)
                })?;
        version.ok_or_else(|| StorageError::Integrity("schema_migrations is empty".to_owned()))
    }

    fn from_connection(connection: Connection) -> Result<Self, StorageError> {
        connection.pragma_update(None, "foreign_keys", "ON")?;
        connection.busy_timeout(Duration::from_secs(5))?;
        Ok(Self { connection })
    }

    fn ensure_private_permissions(path: &Path) -> Result<(), StorageError> {
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;

            let mut permissions = fs::metadata(path)?.permissions();
            permissions.set_mode(0o600);
            fs::set_permissions(path, permissions)?;
        }
        #[cfg(not(unix))]
        {
            let _ = (fs::metadata(path)?, path);
        }
        Ok(())
    }

    fn ensure_parent_directory(path: &Path) -> Result<(), StorageError> {
        let Some(parent) = path.parent() else {
            return Ok(());
        };
        if parent.as_os_str().is_empty() || parent.exists() {
            return Ok(());
        }

        let mut missing = Vec::new();
        let mut current = parent;
        while !current.exists() {
            missing.push(current.to_path_buf());
            let Some(next) = current.parent() else {
                break;
            };
            if next == current {
                break;
            }
            current = next;
        }
        fs::create_dir_all(parent)?;

        #[cfg(unix)]
        for directory in missing {
            use std::os::unix::fs::PermissionsExt;

            let mut permissions = fs::metadata(&directory)?.permissions();
            permissions.set_mode(0o700);
            fs::set_permissions(directory, permissions)?;
        }
        #[cfg(not(unix))]
        let _ = missing;

        Ok(())
    }
}
