use ledgermind_application::{KnowledgeRepository, UnitOfWork};
use ledgermind_domain::{KnowledgeId, KnowledgeInput, KnowledgeItem, MemorySpaceId, Phase};
use ledgermind_storage_sqlite::{Database, SqliteUnitOfWork, StorageError};
use rusqlite::params;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};

fn setup_database() -> (Database, MemorySpaceId) {
    let mut database = Database::open_in_memory().expect("database opens");
    database.migrate().expect("database migrates");
    let memory_space_id = MemorySpaceId::try_from("space-uow").expect("valid memory space id");
    let timestamp = OffsetDateTime::from_unix_timestamp(1_700_000_100)
        .expect("valid timestamp")
        .format(&Rfc3339)
        .expect("timestamp formats");
    database
        .connection_mut()
        .execute(
            "INSERT INTO memory_spaces
                (memory_space_id, display_name, source_client, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?4)",
            params![memory_space_id.as_str(), "UoW", "test", timestamp],
        )
        .expect("memory space inserts");
    (database, memory_space_id)
}

fn sample_knowledge(memory_space_id: &MemorySpaceId) -> KnowledgeItem {
    KnowledgeItem::new(KnowledgeInput {
        knowledge_id: KnowledgeId::try_from("knowledge-uow").expect("valid knowledge id"),
        memory_space_id: memory_space_id.clone(),
        title: "UoW title".to_owned(),
        target: "UoW target".to_owned(),
        statement: "UoW statement".to_owned(),
        rationale: "UoW rationale".to_owned(),
        phase: Phase::Pattern,
        version: 1,
        created_at: OffsetDateTime::from_unix_timestamp(1_700_000_101).expect("valid timestamp"),
        updated_at: OffsetDateTime::from_unix_timestamp(1_700_000_101).expect("valid timestamp"),
        superseded_by_id: None,
        deleted_at: None,
    })
    .expect("valid knowledge")
}

#[test]
fn unit_of_work_rolls_back_repository_writes_and_can_commit_afterward() {
    let (mut database, memory_space_id) = setup_database();
    let knowledge = sample_knowledge(&memory_space_id);

    {
        let mut unit_of_work = SqliteUnitOfWork::new(database.connection_mut());
        let result: Result<(), StorageError> = unit_of_work.transaction(|repositories| {
            repositories.knowledge().add(&knowledge)?;
            Err(StorageError::InvalidRecord("forced rollback".to_owned()))
        });
        assert!(matches!(
            result,
            Err(StorageError::InvalidRecord(message)) if message == "forced rollback"
        ));
    }
    let count: i64 = database
        .connection()
        .query_row(
            "SELECT COUNT(*) FROM knowledge_items WHERE knowledge_id = ?1",
            [knowledge.id().as_str()],
            |row| row.get(0),
        )
        .expect("count after rollback");
    assert_eq!(count, 0);

    {
        let mut unit_of_work = SqliteUnitOfWork::new(database.connection_mut());
        unit_of_work
            .transaction(|repositories| {
                repositories.knowledge().add(&knowledge)?;
                Ok(())
            })
            .expect("successful transaction commits");
    }
    let count: i64 = database
        .connection()
        .query_row(
            "SELECT COUNT(*) FROM knowledge_items WHERE knowledge_id = ?1",
            [knowledge.id().as_str()],
            |row| row.get(0),
        )
        .expect("count after commit");
    assert_eq!(count, 1);
}

#[test]
fn explicit_unit_of_work_lifecycle_is_implemented_by_sqlite_adapter() {
    let (mut database, _) = setup_database();
    let mut unit_of_work = SqliteUnitOfWork::new(database.connection_mut());
    unit_of_work.begin_immediate().expect("begin succeeds");
    unit_of_work.rollback().expect("rollback succeeds");
    unit_of_work
        .begin_immediate()
        .expect("second begin succeeds");
    unit_of_work.commit().expect("commit succeeds");
}
