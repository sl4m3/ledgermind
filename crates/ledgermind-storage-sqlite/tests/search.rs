use ledgermind_application::{KnowledgeRepository, KnowledgeSearch};
use ledgermind_domain::{KnowledgeId, KnowledgeInput, KnowledgeItem, MemorySpaceId, Phase};
use ledgermind_storage_sqlite::{Database, SqliteRepositories, StorageError};
use rusqlite::params;
use time::OffsetDateTime;

fn setup_database() -> (Database, MemorySpaceId, MemorySpaceId) {
    let mut database = Database::open_in_memory().expect("database opens");
    database.migrate().expect("database migrates");
    let first = MemorySpaceId::try_from("memory-space-1").expect("valid first space");
    let second = MemorySpaceId::try_from("memory-space-2").expect("valid second space");
    for memory_space_id in [&first, &second] {
        database
            .connection_mut()
            .execute(
                "INSERT INTO memory_spaces
                    (memory_space_id, display_name, source_client, created_at, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?4)",
                params![
                    memory_space_id.as_str(),
                    "Test space",
                    "stage10-test",
                    "2023-11-14T22:13:20Z"
                ],
            )
            .expect("memory space seed succeeds");
    }
    (database, first, second)
}

fn knowledge(
    memory_space_id: &MemorySpaceId,
    id: &str,
    title: &str,
    statement: &str,
    superseded_by_id: Option<&str>,
) -> KnowledgeItem {
    KnowledgeItem::new(KnowledgeInput {
        knowledge_id: KnowledgeId::try_from(id).expect("valid knowledge id"),
        memory_space_id: memory_space_id.clone(),
        title: title.to_owned(),
        target: "Rust Core".to_owned(),
        statement: statement.to_owned(),
        rationale: "Stage 10 search fixture".to_owned(),
        phase: Phase::Pattern,
        version: 1,
        created_at: OffsetDateTime::from_unix_timestamp(1_700_000_000).expect("valid time"),
        updated_at: OffsetDateTime::from_unix_timestamp(1_700_000_001).expect("valid time"),
        superseded_by_id: superseded_by_id
            .map(|value| KnowledgeId::try_from(value).expect("valid successor id")),
        deleted_at: None,
    })
    .expect("knowledge fixture is valid")
}

#[test]
fn search_is_scoped_to_current_knowledge_and_memory_space() {
    let (database, first, second) = setup_database();
    let repositories = SqliteRepositories::new(database.connection());
    let successor = knowledge(
        &first,
        "knowledge-new",
        "Rust database search",
        "Rust Core uses an SQLite database",
        None,
    );
    let predecessor = knowledge(
        &first,
        "knowledge-old",
        "Old Rust database note",
        "Rust Core used an older database",
        Some("knowledge-new"),
    );
    let other_space = knowledge(
        &second,
        "knowledge-other",
        "Rust database from another space",
        "This must not cross the memory boundary",
        None,
    );
    repositories
        .knowledge()
        .add(&successor)
        .expect("successor persists");
    repositories
        .knowledge()
        .add(&predecessor)
        .expect("predecessor persists");
    repositories
        .knowledge()
        .add(&other_space)
        .expect("other-space knowledge persists");

    let hits = repositories
        .knowledge()
        .search(&first, "Rust database", 10)
        .expect("search succeeds");
    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0].knowledge_id, *successor.id());
    assert!((0.0..=1.0).contains(&hits[0].relevance));
    assert!(repositories.knowledge().search(&first, "", 10).is_err());
    assert!(matches!(
        repositories.knowledge().search(&first, "Rust", 101),
        Err(StorageError::InvalidRecord(_))
    ));
}
