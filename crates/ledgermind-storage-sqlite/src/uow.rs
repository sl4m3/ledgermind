use ledgermind_application::UnitOfWork;
use rusqlite::Connection;

use crate::{SqliteRepositories, StorageError};

pub struct SqliteUnitOfWork<'connection> {
    connection: &'connection mut Connection,
    active: bool,
}

impl<'connection> SqliteUnitOfWork<'connection> {
    pub fn new(connection: &'connection mut Connection) -> Self {
        Self {
            connection,
            active: false,
        }
    }

    pub fn transaction<T, F>(&mut self, operation: F) -> Result<T, StorageError>
    where
        F: FnOnce(&SqliteRepositories<'_>) -> Result<T, StorageError>,
    {
        self.begin_immediate()?;
        let result = {
            let repositories = SqliteRepositories::new(&*self.connection);
            operation(&repositories)
        };
        match result {
            Ok(value) => {
                self.commit()?;
                Ok(value)
            }
            Err(operation_error) => match self.rollback() {
                Ok(()) => Err(operation_error),
                Err(rollback_error) => Err(StorageError::Transaction(format!(
                    "transaction failed: {operation_error}; rollback failed: {rollback_error}"
                ))),
            },
        }
    }
}

impl UnitOfWork for SqliteUnitOfWork<'_> {
    type Error = StorageError;

    fn begin_immediate(&mut self) -> Result<(), Self::Error> {
        if self.active {
            return Err(StorageError::Transaction(
                "transaction is already active".to_owned(),
            ));
        }
        self.connection.execute_batch("BEGIN IMMEDIATE")?;
        self.active = true;
        Ok(())
    }

    fn commit(&mut self) -> Result<(), Self::Error> {
        if !self.active {
            return Err(StorageError::Transaction(
                "transaction is not active".to_owned(),
            ));
        }
        self.connection.execute_batch("COMMIT")?;
        self.active = false;
        Ok(())
    }

    fn rollback(&mut self) -> Result<(), Self::Error> {
        if !self.active {
            return Err(StorageError::Transaction(
                "transaction is not active".to_owned(),
            ));
        }
        self.connection.execute_batch("ROLLBACK")?;
        self.active = false;
        Ok(())
    }
}

impl Drop for SqliteUnitOfWork<'_> {
    fn drop(&mut self) {
        if self.active {
            let _ = self.connection.execute_batch("ROLLBACK");
            self.active = false;
        }
    }
}
