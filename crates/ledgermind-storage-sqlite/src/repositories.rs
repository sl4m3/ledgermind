use std::fmt::Display;

use ledgermind_application::{
    ContextUsageRecord, ContextUsageRepository, EvidenceRepository, HypothesisRepository,
    IdempotencyRepository, KnowledgeRepository, KnowledgeSearch, KnowledgeSearchHit,
    ModelTaskRecord, ModelTaskRepository, ModelTaskSubmission, ProjectionEventRecord,
    ProjectionEventRepository, RevisionRepository, StoredIdempotencyResult,
};
use ledgermind_domain::{
    EvidenceLink, EvidenceRelation, Hypothesis, HypothesisEvidence, HypothesisExtraction,
    HypothesisId, IdempotencyKey, KnowledgeId, KnowledgeItem, KnowledgeRevision, MemorySpaceId,
    ModelTaskId, Phase, ProjectionEventId, RevisionId,
};
use rusqlite::{Connection, OptionalExtension, Row, params};
use time::{OffsetDateTime, format_description::well_known::Rfc3339};

use crate::StorageError;

pub struct SqliteRepositories<'connection> {
    hypotheses: SqliteHypothesisRepository<'connection>,
    knowledge: SqliteKnowledgeRepository<'connection>,
    revisions: SqliteRevisionRepository<'connection>,
    evidence: SqliteEvidenceRepository<'connection>,
    idempotency: SqliteIdempotencyRepository<'connection>,
    model_tasks: SqliteModelTaskRepository<'connection>,
    projection_events: SqliteProjectionEventRepository<'connection>,
    context_usage: SqliteContextUsageRepository<'connection>,
}

impl<'connection> SqliteRepositories<'connection> {
    pub fn new(connection: &'connection Connection) -> Self {
        Self {
            hypotheses: SqliteHypothesisRepository { connection },
            knowledge: SqliteKnowledgeRepository { connection },
            revisions: SqliteRevisionRepository { connection },
            evidence: SqliteEvidenceRepository { connection },
            idempotency: SqliteIdempotencyRepository { connection },
            model_tasks: SqliteModelTaskRepository { connection },
            projection_events: SqliteProjectionEventRepository { connection },
            context_usage: SqliteContextUsageRepository { connection },
        }
    }

    pub fn hypotheses(&self) -> &SqliteHypothesisRepository<'connection> {
        &self.hypotheses
    }

    pub fn connection(&self) -> &'connection Connection {
        self.hypotheses.connection
    }

    pub fn knowledge(&self) -> &SqliteKnowledgeRepository<'connection> {
        &self.knowledge
    }

    pub fn revisions(&self) -> &SqliteRevisionRepository<'connection> {
        &self.revisions
    }

    pub fn evidence(&self) -> &SqliteEvidenceRepository<'connection> {
        &self.evidence
    }

    pub fn idempotency(&self) -> &SqliteIdempotencyRepository<'connection> {
        &self.idempotency
    }

    pub fn model_tasks(&self) -> &SqliteModelTaskRepository<'connection> {
        &self.model_tasks
    }

    pub fn projection_events(&self) -> &SqliteProjectionEventRepository<'connection> {
        &self.projection_events
    }

    pub fn context_usage(&self) -> &SqliteContextUsageRepository<'connection> {
        &self.context_usage
    }
}

pub struct SqliteHypothesisRepository<'connection> {
    connection: &'connection Connection,
}

impl HypothesisRepository for SqliteHypothesisRepository<'_> {
    type Error = StorageError;

    fn add(&self, hypothesis: &Hypothesis) -> Result<(), Self::Error> {
        self.connection.execute(
            "INSERT INTO hypotheses (
                hypothesis_id, memory_space_id, content_digest, title, target, statement,
                rationale, result, artifacts_json, source_system, source_instance_id,
                source_profile_id, source_session_id, source_round_id, source_event_ids_json,
                raw_round_digest, normalized_round_digest, provider, model, prompt_version,
                schema_version, completed_at, created_at
            ) VALUES (
                ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15,
                ?16, ?17, ?18, ?19, ?20, ?21, ?22, ?23
            )",
            params![
                hypothesis.id().as_str(),
                hypothesis.memory_space_id().as_str(),
                hypothesis.content_digest().as_str(),
                hypothesis.title(),
                hypothesis.target(),
                hypothesis.statement(),
                hypothesis.rationale(),
                hypothesis.result(),
                serde_json::to_string(hypothesis.artifacts())?,
                hypothesis.evidence().source_system(),
                hypothesis.evidence().source_instance_id(),
                hypothesis.evidence().source_profile_id(),
                hypothesis.evidence().source_session_id(),
                hypothesis.evidence().source_round_id(),
                serde_json::to_string(hypothesis.evidence().source_event_ids())?,
                hypothesis.evidence().raw_round_digest().as_str(),
                hypothesis.evidence().normalized_round_digest().as_str(),
                hypothesis.extraction().provider(),
                hypothesis.extraction().model(),
                sql_u64(
                    u64::from(hypothesis.extraction().prompt_version()),
                    "prompt_version",
                )?,
                sql_u64(
                    u64::from(hypothesis.extraction().schema_version()),
                    "schema_version",
                )?,
                encode_time(hypothesis.extraction().completed_at())?,
                encode_time(hypothesis.created_at())?,
            ],
        )?;
        Ok(())
    }

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        hypothesis_id: &HypothesisId,
    ) -> Result<Option<Hypothesis>, Self::Error> {
        let row = self
            .connection
            .query_row(
                "SELECT hypothesis_id, memory_space_id, content_digest, title, target,
                        statement, rationale, result, artifacts_json, source_system,
                        source_instance_id, source_profile_id, source_session_id,
                        source_round_id, source_event_ids_json, raw_round_digest,
                        normalized_round_digest, provider, model, prompt_version,
                        schema_version, completed_at, created_at
                 FROM hypotheses
                 WHERE memory_space_id = ?1 AND hypothesis_id = ?2",
                params![memory_space_id.as_str(), hypothesis_id.as_str()],
                hypothesis_row_from_sql,
            )
            .optional()?;
        row.map(HypothesisRow::into_domain).transpose()
    }
}

struct HypothesisRow {
    hypothesis_id: String,
    memory_space_id: String,
    content_digest: String,
    title: String,
    target: String,
    statement: String,
    rationale: String,
    result: String,
    artifacts_json: String,
    source_system: String,
    source_instance_id: String,
    source_profile_id: String,
    source_session_id: String,
    source_round_id: String,
    source_event_ids_json: String,
    raw_round_digest: String,
    normalized_round_digest: String,
    provider: String,
    model: String,
    prompt_version: i64,
    schema_version: i64,
    completed_at: String,
    created_at: String,
}

fn hypothesis_row_from_sql(row: &Row<'_>) -> rusqlite::Result<HypothesisRow> {
    Ok(HypothesisRow {
        hypothesis_id: row.get(0)?,
        memory_space_id: row.get(1)?,
        content_digest: row.get(2)?,
        title: row.get(3)?,
        target: row.get(4)?,
        statement: row.get(5)?,
        rationale: row.get(6)?,
        result: row.get(7)?,
        artifacts_json: row.get(8)?,
        source_system: row.get(9)?,
        source_instance_id: row.get(10)?,
        source_profile_id: row.get(11)?,
        source_session_id: row.get(12)?,
        source_round_id: row.get(13)?,
        source_event_ids_json: row.get(14)?,
        raw_round_digest: row.get(15)?,
        normalized_round_digest: row.get(16)?,
        provider: row.get(17)?,
        model: row.get(18)?,
        prompt_version: row.get(19)?,
        schema_version: row.get(20)?,
        completed_at: row.get(21)?,
        created_at: row.get(22)?,
    })
}

impl HypothesisRow {
    fn into_domain(self) -> Result<Hypothesis, StorageError> {
        let hypothesis_id = parse_identifier(self.hypothesis_id, "hypothesis_id")?;
        let memory_space_id = parse_identifier(self.memory_space_id, "memory_space_id")?;
        let content_digest = parse_identifier(self.content_digest, "content_digest")?;
        let raw_round_digest = parse_identifier(self.raw_round_digest, "raw_round_digest")?;
        let normalized_round_digest =
            parse_identifier(self.normalized_round_digest, "normalized_round_digest")?;
        let source_event_ids = decode_json(&self.source_event_ids_json, "source_event_ids_json")?;
        let artifacts = decode_json(&self.artifacts_json, "artifacts_json")?;
        let evidence = HypothesisEvidence::new(
            self.source_system,
            self.source_instance_id,
            self.source_profile_id,
            self.source_session_id,
            self.source_round_id,
            raw_round_digest,
            normalized_round_digest,
            source_event_ids,
        )?;
        let extraction = HypothesisExtraction::new(
            self.provider,
            self.model,
            u32_from_sql(self.prompt_version, "prompt_version")?,
            u32_from_sql(self.schema_version, "schema_version")?,
            decode_time(self.completed_at, "completed_at")?,
        )?;
        Ok(Hypothesis::new(ledgermind_domain::HypothesisInput {
            hypothesis_id,
            memory_space_id,
            content_digest,
            title: self.title,
            target: self.target,
            statement: self.statement,
            rationale: self.rationale,
            result: self.result,
            artifacts,
            evidence,
            extraction,
            created_at: decode_time(self.created_at, "created_at")?,
        })?)
    }
}

pub struct SqliteKnowledgeRepository<'connection> {
    connection: &'connection Connection,
}

impl KnowledgeRepository for SqliteKnowledgeRepository<'_> {
    type Error = StorageError;

    fn add(&self, item: &KnowledgeItem) -> Result<(), Self::Error> {
        self.connection.execute(
            "INSERT INTO knowledge_items (
                knowledge_id, memory_space_id, title, target, statement, rationale,
                phase, version, current_revision_id, created_at, updated_at,
                superseded_by_id, deleted_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, NULL, ?9, ?10, ?11, ?12)",
            params![
                item.id().as_str(),
                item.memory_space_id().as_str(),
                item.title(),
                item.target(),
                item.statement(),
                item.rationale(),
                item.phase().as_str(),
                sql_u64(item.version(), "version")?,
                encode_time(item.created_at())?,
                encode_time(item.updated_at())?,
                item.superseded_by_id().map(ToString::to_string),
                encode_optional_time(item.deleted_at())?,
            ],
        )?;
        replace_knowledge_fts(self.connection, item)?;
        Ok(())
    }

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        knowledge_id: &KnowledgeId,
    ) -> Result<Option<KnowledgeItem>, Self::Error> {
        let row = self
            .connection
            .query_row(
                "SELECT knowledge_id, memory_space_id, title, target, statement, rationale,
                        phase, version, created_at, updated_at, superseded_by_id, deleted_at
                 FROM knowledge_items
                 WHERE memory_space_id = ?1 AND knowledge_id = ?2",
                params![memory_space_id.as_str(), knowledge_id.as_str()],
                knowledge_row_from_sql,
            )
            .optional()?;
        row.map(KnowledgeRow::into_domain).transpose()
    }

    fn update(&self, item: &KnowledgeItem, expected_version: u64) -> Result<(), Self::Error> {
        let changed = self.connection.execute(
            "UPDATE knowledge_items
             SET title = ?1, target = ?2, statement = ?3, rationale = ?4, phase = ?5,
                 version = ?6, updated_at = ?7, superseded_by_id = ?8, deleted_at = ?9
             WHERE knowledge_id = ?10 AND memory_space_id = ?11 AND version = ?12",
            params![
                item.title(),
                item.target(),
                item.statement(),
                item.rationale(),
                item.phase().as_str(),
                sql_u64(item.version(), "version")?,
                encode_time(item.updated_at())?,
                item.superseded_by_id().map(ToString::to_string),
                encode_optional_time(item.deleted_at())?,
                item.id().as_str(),
                item.memory_space_id().as_str(),
                sql_u64(expected_version, "expected_version")?,
            ],
        )?;
        if changed == 1 {
            replace_knowledge_fts(self.connection, item)?;
            return Ok(());
        }

        let actual = self
            .connection
            .query_row(
                "SELECT version FROM knowledge_items
                 WHERE knowledge_id = ?1 AND memory_space_id = ?2",
                params![item.id().as_str(), item.memory_space_id().as_str()],
                |row| row.get::<_, i64>(0),
            )
            .optional()?;
        match actual {
            Some(actual) => Err(StorageError::VersionConflict {
                knowledge_id: item.id().to_string(),
                expected: expected_version,
                actual: u64_from_sql(actual, "version")?,
            }),
            None => Err(StorageError::NotFound(format!(
                "knowledge item {} in memory space {}",
                item.id(),
                item.memory_space_id()
            ))),
        }
    }
}

fn replace_knowledge_fts(
    connection: &Connection,
    item: &KnowledgeItem,
) -> Result<(), StorageError> {
    connection.execute(
        "DELETE FROM knowledge_items_fts
         WHERE knowledge_id = ?1 AND memory_space_id = ?2",
        params![item.id().as_str(), item.memory_space_id().as_str()],
    )?;
    connection.execute(
        "INSERT INTO knowledge_items_fts
            (knowledge_id, memory_space_id, title, target, statement)
         VALUES (?1, ?2, ?3, ?4, ?5)",
        params![
            item.id().as_str(),
            item.memory_space_id().as_str(),
            item.title(),
            item.target(),
            item.statement(),
        ],
    )?;
    Ok(())
}

struct KnowledgeRow {
    knowledge_id: String,
    memory_space_id: String,
    title: String,
    target: String,
    statement: String,
    rationale: String,
    phase: String,
    version: i64,
    created_at: String,
    updated_at: String,
    superseded_by_id: Option<String>,
    deleted_at: Option<String>,
}

fn knowledge_row_from_sql(row: &Row<'_>) -> rusqlite::Result<KnowledgeRow> {
    Ok(KnowledgeRow {
        knowledge_id: row.get(0)?,
        memory_space_id: row.get(1)?,
        title: row.get(2)?,
        target: row.get(3)?,
        statement: row.get(4)?,
        rationale: row.get(5)?,
        phase: row.get(6)?,
        version: row.get(7)?,
        created_at: row.get(8)?,
        updated_at: row.get(9)?,
        superseded_by_id: row.get(10)?,
        deleted_at: row.get(11)?,
    })
}

impl KnowledgeRow {
    fn into_domain(self) -> Result<KnowledgeItem, StorageError> {
        Ok(KnowledgeItem::new(ledgermind_domain::KnowledgeInput {
            knowledge_id: parse_identifier(self.knowledge_id, "knowledge_id")?,
            memory_space_id: parse_identifier(self.memory_space_id, "memory_space_id")?,
            title: self.title,
            target: self.target,
            statement: self.statement,
            rationale: self.rationale,
            phase: Phase::try_from(self.phase)?,
            version: u64_from_sql(self.version, "version")?,
            created_at: decode_time(self.created_at, "created_at")?,
            updated_at: decode_time(self.updated_at, "updated_at")?,
            superseded_by_id: self
                .superseded_by_id
                .map(|value| parse_identifier(value, "superseded_by_id"))
                .transpose()?,
            deleted_at: self
                .deleted_at
                .map(|value| decode_time(value, "deleted_at"))
                .transpose()?,
        })?)
    }
}

impl KnowledgeSearch for SqliteKnowledgeRepository<'_> {
    type Error = StorageError;

    fn search(
        &self,
        memory_space_id: &MemorySpaceId,
        query: &str,
        limit: u32,
    ) -> Result<Vec<KnowledgeSearchHit>, Self::Error> {
        if query.trim().is_empty() {
            return Err(StorageError::InvalidRecord(
                "search query must not be empty".to_owned(),
            ));
        }
        if !(1..=100).contains(&limit) {
            return Err(StorageError::InvalidRecord(
                "search limit must be between 1 and 100".to_owned(),
            ));
        }
        let mut statement = self.connection.prepare(
            "SELECT f.knowledge_id, k.title, k.target, k.statement,
                    bm25(knowledge_items_fts) AS rank
             FROM knowledge_items_fts f
             JOIN knowledge_items k ON k.knowledge_id = f.knowledge_id
                 AND k.memory_space_id = f.memory_space_id
             WHERE f.memory_space_id = ?1
               AND knowledge_items_fts MATCH ?2
               AND k.deleted_at IS NULL
               AND k.superseded_by_id IS NULL
             ORDER BY rank ASC
             LIMIT ?3",
        )?;
        let rows = statement.query_map(
            params![memory_space_id.as_str(), query, i64::from(limit)],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, f64>(4)?,
                ))
            },
        )?;
        rows.map(|row| {
            let (knowledge_id, title, target, statement, rank) = row?;
            Ok(KnowledgeSearchHit {
                knowledge_id: parse_identifier(knowledge_id, "knowledge_id")?,
                title,
                target,
                statement,
                relevance: (1.0 / (1.0 + rank.abs())).clamp(0.0, 1.0),
            })
        })
        .collect()
    }
}

pub struct SqliteRevisionRepository<'connection> {
    connection: &'connection Connection,
}

impl RevisionRepository for SqliteRevisionRepository<'_> {
    type Error = StorageError;

    fn add(&self, revision: &KnowledgeRevision) -> Result<(), Self::Error> {
        let knowledge_id = revision.knowledge_id();
        let version = sql_u64(revision.version(), "version")?;
        let memory_space_id: Option<String> = self
            .connection
            .query_row(
                "SELECT memory_space_id FROM knowledge_items
                 WHERE knowledge_id = ?1 AND version = ?2",
                params![knowledge_id.as_str(), version],
                |row| row.get(0),
            )
            .optional()?;
        let Some(memory_space_id) = memory_space_id else {
            return Err(StorageError::VersionConflict {
                knowledge_id: knowledge_id.to_string(),
                expected: revision.version(),
                actual: 0,
            });
        };

        self.connection.execute(
            "INSERT INTO knowledge_revisions (
                revision_id, knowledge_id, version, event_type, snapshot_json,
                cause_hypothesis_id, created_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                revision.revision_id().as_str(),
                knowledge_id.as_str(),
                version,
                revision.event_type(),
                revision.snapshot_json(),
                revision.cause_hypothesis_id().map(ToString::to_string),
                encode_time(revision.created_at())?,
            ],
        )?;
        self.connection.execute(
            "UPDATE knowledge_items SET current_revision_id = ?1
             WHERE knowledge_id = ?2 AND version = ?3",
            params![
                revision.revision_id().as_str(),
                knowledge_id.as_str(),
                version
            ],
        )?;
        let _ = memory_space_id;
        Ok(())
    }

    fn list_for_knowledge(
        &self,
        memory_space_id: &MemorySpaceId,
        knowledge_id: &KnowledgeId,
    ) -> Result<Vec<KnowledgeRevision>, Self::Error> {
        let mut statement = self.connection.prepare(
            "SELECT r.revision_id, r.knowledge_id, r.version, r.event_type,
                    r.snapshot_json, r.cause_hypothesis_id, r.created_at
             FROM knowledge_revisions r
             JOIN knowledge_items k ON k.knowledge_id = r.knowledge_id
             WHERE k.memory_space_id = ?1 AND r.knowledge_id = ?2
             ORDER BY r.version",
        )?;
        let rows = statement.query_map(
            params![memory_space_id.as_str(), knowledge_id.as_str()],
            |row| {
                Ok(RevisionRow {
                    revision_id: row.get(0)?,
                    knowledge_id: row.get(1)?,
                    version: row.get(2)?,
                    event_type: row.get(3)?,
                    snapshot_json: row.get(4)?,
                    cause_hypothesis_id: row.get(5)?,
                    created_at: row.get(6)?,
                })
            },
        )?;
        rows.map(|row| {
            row.map_err(StorageError::from)
                .and_then(RevisionRow::into_domain)
        })
        .collect()
    }

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        revision_id: &RevisionId,
    ) -> Result<Option<KnowledgeRevision>, Self::Error> {
        let row = self
            .connection
            .query_row(
                "SELECT r.revision_id, r.knowledge_id, r.version, r.event_type,
                        r.snapshot_json, r.cause_hypothesis_id, r.created_at
                 FROM knowledge_revisions r
                 JOIN knowledge_items k ON k.knowledge_id = r.knowledge_id
                 WHERE k.memory_space_id = ?1 AND r.revision_id = ?2",
                params![memory_space_id.as_str(), revision_id.as_str()],
                |row| {
                    Ok(RevisionRow {
                        revision_id: row.get(0)?,
                        knowledge_id: row.get(1)?,
                        version: row.get(2)?,
                        event_type: row.get(3)?,
                        snapshot_json: row.get(4)?,
                        cause_hypothesis_id: row.get(5)?,
                        created_at: row.get(6)?,
                    })
                },
            )
            .optional()?;
        row.map(RevisionRow::into_domain).transpose()
    }
}

struct RevisionRow {
    revision_id: String,
    knowledge_id: String,
    version: i64,
    event_type: String,
    snapshot_json: String,
    cause_hypothesis_id: Option<String>,
    created_at: String,
}

impl RevisionRow {
    fn into_domain(self) -> Result<KnowledgeRevision, StorageError> {
        Ok(KnowledgeRevision::from_json(
            parse_identifier(self.revision_id, "revision_id")?,
            parse_identifier(self.knowledge_id, "knowledge_id")?,
            u64_from_sql(self.version, "version")?,
            self.event_type,
            self.snapshot_json,
            self.cause_hypothesis_id
                .map(|value| parse_identifier(value, "cause_hypothesis_id"))
                .transpose()?,
            decode_time(self.created_at, "created_at")?,
        )?)
    }
}

pub struct SqliteEvidenceRepository<'connection> {
    connection: &'connection Connection,
}

impl EvidenceRepository for SqliteEvidenceRepository<'_> {
    type Error = StorageError;

    fn add(&self, link: &EvidenceLink) -> Result<(), Self::Error> {
        let knowledge_space: Option<String> = self
            .connection
            .query_row(
                "SELECT memory_space_id FROM knowledge_items WHERE knowledge_id = ?1",
                [link.knowledge_id().as_str()],
                |row| row.get(0),
            )
            .optional()?;
        let hypothesis_space: Option<String> = self
            .connection
            .query_row(
                "SELECT memory_space_id FROM hypotheses WHERE hypothesis_id = ?1",
                [link.hypothesis_id().as_str()],
                |row| row.get(0),
            )
            .optional()?;
        let (Some(knowledge_space), Some(hypothesis_space)) = (knowledge_space, hypothesis_space)
        else {
            return Err(StorageError::NotFound("evidence endpoint".to_owned()));
        };
        if knowledge_space != hypothesis_space {
            return Err(StorageError::Integrity(
                "evidence endpoints belong to different memory spaces".to_owned(),
            ));
        }

        self.connection.execute(
            "INSERT INTO evidence_links
                (knowledge_id, hypothesis_id, relation, created_at)
             VALUES (?1, ?2, ?3, ?4)",
            params![
                link.knowledge_id().as_str(),
                link.hypothesis_id().as_str(),
                link.relation().as_str(),
                encode_time(link.created_at())?,
            ],
        )?;
        Ok(())
    }

    fn count_for_knowledge(
        &self,
        memory_space_id: &MemorySpaceId,
        knowledge_id: &KnowledgeId,
    ) -> Result<u64, Self::Error> {
        let count: i64 = self.connection.query_row(
            "SELECT COUNT(*) FROM evidence_links e
             JOIN knowledge_items k ON k.knowledge_id = e.knowledge_id
             WHERE k.memory_space_id = ?1 AND e.knowledge_id = ?2",
            params![memory_space_id.as_str(), knowledge_id.as_str()],
            |row| row.get(0),
        )?;
        u64_from_sql(count, "evidence count")
    }

    fn list_for_knowledge(
        &self,
        memory_space_id: &MemorySpaceId,
        knowledge_id: &KnowledgeId,
    ) -> Result<Vec<EvidenceLink>, Self::Error> {
        let mut statement = self.connection.prepare(
            "SELECT e.knowledge_id, e.hypothesis_id, e.relation, e.created_at
             FROM evidence_links e
             JOIN knowledge_items k ON k.knowledge_id = e.knowledge_id
             WHERE k.memory_space_id = ?1 AND e.knowledge_id = ?2
             ORDER BY e.created_at",
        )?;
        let rows = statement.query_map(
            params![memory_space_id.as_str(), knowledge_id.as_str()],
            |row| {
                Ok(EvidenceRow {
                    knowledge_id: row.get(0)?,
                    hypothesis_id: row.get(1)?,
                    relation: row.get(2)?,
                    created_at: row.get(3)?,
                })
            },
        )?;
        rows.map(|row| {
            row.map_err(StorageError::from)
                .and_then(EvidenceRow::into_domain)
        })
        .collect()
    }
}

struct EvidenceRow {
    knowledge_id: String,
    hypothesis_id: String,
    relation: String,
    created_at: String,
}

impl EvidenceRow {
    fn into_domain(self) -> Result<EvidenceLink, StorageError> {
        Ok(EvidenceLink::new(
            parse_identifier(self.knowledge_id, "knowledge_id")?,
            parse_identifier(self.hypothesis_id, "hypothesis_id")?,
            parse_evidence_relation(&self.relation)?,
            decode_time(self.created_at, "created_at")?,
        ))
    }
}

pub struct SqliteIdempotencyRepository<'connection> {
    connection: &'connection Connection,
}

impl IdempotencyRepository for SqliteIdempotencyRepository<'_> {
    type Error = StorageError;

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        idempotency_key: &IdempotencyKey,
    ) -> Result<Option<StoredIdempotencyResult>, Self::Error> {
        let row = self
            .connection
            .query_row(
                "SELECT memory_space_id, idempotency_key, request_hash, response_json,
                        created_at, expires_at
                 FROM idempotency_results
                 WHERE memory_space_id = ?1 AND idempotency_key = ?2",
                params![memory_space_id.as_str(), idempotency_key.as_str()],
                |row| {
                    Ok(IdempotencyRow {
                        memory_space_id: row.get(0)?,
                        idempotency_key: row.get(1)?,
                        request_hash: row.get(2)?,
                        response_json: row.get(3)?,
                        created_at: row.get(4)?,
                        expires_at: row.get(5)?,
                    })
                },
            )
            .optional()?;
        row.map(IdempotencyRow::into_domain).transpose()
    }

    fn put(&self, result: &StoredIdempotencyResult) -> Result<(), Self::Error> {
        let existing: Option<(String, String)> = self
            .connection
            .query_row(
                "SELECT request_hash, response_json FROM idempotency_results
                 WHERE memory_space_id = ?1 AND idempotency_key = ?2",
                params![
                    result.memory_space_id.as_str(),
                    result.idempotency_key.as_str()
                ],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        if let Some((request_hash, response_json)) = existing {
            if request_hash == result.request_hash.as_str() && response_json == result.response_json
            {
                return Ok(());
            }
            return Err(StorageError::IdempotencyConflict {
                memory_space_id: result.memory_space_id.to_string(),
                key: result.idempotency_key.to_string(),
            });
        }

        self.connection.execute(
            "INSERT INTO idempotency_results
                (memory_space_id, idempotency_key, request_hash, response_json, created_at, expires_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                result.memory_space_id.as_str(),
                result.idempotency_key.as_str(),
                result.request_hash.as_str(),
                result.response_json,
                encode_time(result.created_at)?,
                encode_optional_time(result.expires_at)?,
            ],
        )?;
        Ok(())
    }
}

struct IdempotencyRow {
    memory_space_id: String,
    idempotency_key: String,
    request_hash: String,
    response_json: String,
    created_at: String,
    expires_at: Option<String>,
}

impl IdempotencyRow {
    fn into_domain(self) -> Result<StoredIdempotencyResult, StorageError> {
        Ok(StoredIdempotencyResult {
            memory_space_id: parse_identifier(self.memory_space_id, "memory_space_id")?,
            idempotency_key: parse_identifier(self.idempotency_key, "idempotency_key")?,
            request_hash: parse_identifier(self.request_hash, "request_hash")?,
            response_json: self.response_json,
            created_at: decode_time(self.created_at, "created_at")?,
            expires_at: self
                .expires_at
                .map(|value| decode_time(value, "expires_at"))
                .transpose()?,
        })
    }
}

pub struct SqliteModelTaskRepository<'connection> {
    connection: &'connection Connection,
}

impl ModelTaskRepository for SqliteModelTaskRepository<'_> {
    type Error = StorageError;

    fn add(&self, task: &ModelTaskRecord) -> Result<(), Self::Error> {
        self.connection.execute(
            "INSERT INTO model_tasks (
                task_id, memory_space_id, task_type, status, request_digest,
                payload_json, result_json, created_at, updated_at, expires_at,
                lease_owner, lease_expires_at, attempts
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
            params![
                task.task_id.as_str(),
                task.memory_space_id.as_str(),
                task.task_type,
                task.status,
                task.request_digest.as_str(),
                task.payload_json,
                task.result_json,
                encode_time(task.created_at)?,
                encode_time(task.updated_at)?,
                encode_optional_time(task.expires_at)?,
                task.lease_owner,
                encode_optional_time(task.lease_expires_at)?,
                i64::from(task.attempts),
            ],
        )?;
        Ok(())
    }

    fn get(
        &self,
        memory_space_id: &MemorySpaceId,
        task_id: &ModelTaskId,
    ) -> Result<Option<ModelTaskRecord>, Self::Error> {
        let row = self
            .connection
            .query_row(
                "SELECT task_id, memory_space_id, task_type, status, request_digest,
                        payload_json, result_json, created_at, updated_at, expires_at,
                        lease_owner, lease_expires_at, attempts
                 FROM model_tasks
                 WHERE memory_space_id = ?1 AND task_id = ?2",
                params![memory_space_id.as_str(), task_id.as_str()],
                model_task_row_from_sql,
            )
            .optional()?;
        row.map(ModelTaskRow::into_domain).transpose()
    }

    fn update(&self, task: &ModelTaskRecord) -> Result<(), Self::Error> {
        let changed = self.connection.execute(
            "UPDATE model_tasks SET task_type = ?1, status = ?2, request_digest = ?3,
                payload_json = ?4, result_json = ?5, updated_at = ?6, expires_at = ?7,
                lease_owner = ?8, lease_expires_at = ?9, attempts = ?10
             WHERE task_id = ?11 AND memory_space_id = ?12",
            params![
                task.task_type,
                task.status,
                task.request_digest.as_str(),
                task.payload_json,
                task.result_json,
                encode_time(task.updated_at)?,
                encode_optional_time(task.expires_at)?,
                task.lease_owner,
                encode_optional_time(task.lease_expires_at)?,
                i64::from(task.attempts),
                task.task_id.as_str(),
                task.memory_space_id.as_str(),
            ],
        )?;
        if changed == 0 {
            return Err(StorageError::NotFound(format!(
                "model task {}",
                task.task_id
            )));
        }
        Ok(())
    }

    fn claim_for_worker(
        &self,
        memory_space_id: &MemorySpaceId,
        worker_id: &str,
        now: OffsetDateTime,
        lease_duration: time::Duration,
        limit: u32,
    ) -> Result<(Vec<ModelTaskRecord>, bool), Self::Error> {
        if worker_id.trim().is_empty() || limit == 0 || lease_duration.is_negative() {
            return Err(StorageError::InvalidRecord(
                "model task lease request is invalid".to_owned(),
            ));
        }
        let now_text = encode_time(now)?;
        let lease_expires_at = now + lease_duration;
        let lease_expires_text = encode_time(lease_expires_at)?;
        self.connection.execute(
            "UPDATE model_tasks
             SET status = 'expired', lease_owner = NULL, lease_expires_at = NULL,
                 updated_at = ?1
             WHERE memory_space_id = ?2
               AND status NOT IN ('completed', 'expired')
               AND expires_at IS NOT NULL
               AND expires_at <= ?1",
            params![now_text, memory_space_id.as_str()],
        )?;

        let selection_limit = i64::from(limit) + 1;
        let mut statement = self.connection.prepare(
            "SELECT task_id, memory_space_id, task_type, status, request_digest,
                    payload_json, result_json, created_at, updated_at, expires_at,
                    lease_owner, lease_expires_at, attempts
             FROM model_tasks
             WHERE memory_space_id = ?1
               AND (status IN ('queued', 'retry_wait')
                    OR (status = 'leased' AND lease_expires_at <= ?2))
               AND (expires_at IS NULL OR expires_at > ?2)
             ORDER BY created_at, task_id
             LIMIT ?3",
        )?;
        let rows = statement
            .query_map(
                params![memory_space_id.as_str(), now_text, selection_limit],
                model_task_row_from_sql,
            )?
            .collect::<Result<Vec<_>, rusqlite::Error>>()?;
        drop(statement);

        let has_more = rows.len() > limit as usize;
        let mut claimed = Vec::with_capacity(rows.len().min(limit as usize));
        for row in rows.into_iter().take(limit as usize) {
            let mut task = row.into_domain()?;
            let changed = self.connection.execute(
                "UPDATE model_tasks
                 SET status = 'leased', lease_owner = ?1, lease_expires_at = ?2,
                     attempts = attempts + 1, updated_at = ?3
                 WHERE task_id = ?4 AND memory_space_id = ?5
                   AND (status IN ('queued', 'retry_wait')
                        OR (status = 'leased' AND lease_expires_at <= ?3))
                   AND (expires_at IS NULL OR expires_at > ?3)",
                params![
                    worker_id,
                    lease_expires_text,
                    now_text,
                    task.task_id.as_str(),
                    memory_space_id.as_str(),
                ],
            )?;
            if changed == 0 {
                continue;
            }
            task.status = "leased".to_owned();
            task.lease_owner = Some(worker_id.to_owned());
            task.lease_expires_at = Some(lease_expires_at);
            task.updated_at = now;
            task.attempts = task.attempts.saturating_add(1);
            claimed.push(task);
        }
        Ok((claimed, has_more))
    }

    fn submit_result(
        &self,
        memory_space_id: &MemorySpaceId,
        task_id: &ModelTaskId,
        worker_id: &str,
        result_json: String,
        now: OffsetDateTime,
    ) -> Result<ModelTaskSubmission, Self::Error> {
        let task = self
            .get(memory_space_id, task_id)?
            .ok_or_else(|| StorageError::NotFound(format!("model task {task_id}")))?;
        if task.status == "completed" {
            if task.result_json.as_deref() == Some(result_json.as_str()) {
                return Ok(ModelTaskSubmission {
                    accepted: true,
                    duplicate: true,
                    status: "completed".to_owned(),
                });
            }
            return Err(StorageError::IdempotencyConflict {
                memory_space_id: memory_space_id.to_string(),
                key: task_id.to_string(),
            });
        }
        if task.status != "leased"
            || task.lease_owner.as_deref() != Some(worker_id)
            || task
                .lease_expires_at
                .is_none_or(|lease_expires_at| lease_expires_at <= now)
            || task.expires_at.is_some_and(|expires_at| expires_at <= now)
        {
            return Err(StorageError::StaleModelTask(format!(
                "task {task_id} is not owned by an active lease"
            )));
        }
        let changed = self.connection.execute(
            "UPDATE model_tasks
             SET status = 'completed', result_json = ?1, lease_owner = NULL,
                 lease_expires_at = NULL, updated_at = ?2
             WHERE task_id = ?3 AND memory_space_id = ?4 AND status = 'leased'
               AND lease_owner = ?5 AND lease_expires_at > ?2",
            params![
                result_json,
                encode_time(now)?,
                task_id.as_str(),
                memory_space_id.as_str(),
                worker_id,
            ],
        )?;
        if changed == 0 {
            return Err(StorageError::StaleModelTask(format!(
                "task {task_id} lease was lost"
            )));
        }
        Ok(ModelTaskSubmission {
            accepted: true,
            duplicate: false,
            status: "completed".to_owned(),
        })
    }
}

struct ModelTaskRow {
    task_id: String,
    memory_space_id: String,
    task_type: String,
    status: String,
    request_digest: String,
    payload_json: String,
    result_json: Option<String>,
    created_at: String,
    updated_at: String,
    expires_at: Option<String>,
    lease_owner: Option<String>,
    lease_expires_at: Option<String>,
    attempts: i64,
}

fn model_task_row_from_sql(row: &Row<'_>) -> rusqlite::Result<ModelTaskRow> {
    Ok(ModelTaskRow {
        task_id: row.get(0)?,
        memory_space_id: row.get(1)?,
        task_type: row.get(2)?,
        status: row.get(3)?,
        request_digest: row.get(4)?,
        payload_json: row.get(5)?,
        result_json: row.get(6)?,
        created_at: row.get(7)?,
        updated_at: row.get(8)?,
        expires_at: row.get(9)?,
        lease_owner: row.get(10)?,
        lease_expires_at: row.get(11)?,
        attempts: row.get(12)?,
    })
}

impl ModelTaskRow {
    fn into_domain(self) -> Result<ModelTaskRecord, StorageError> {
        Ok(ModelTaskRecord {
            task_id: parse_identifier(self.task_id, "task_id")?,
            memory_space_id: parse_identifier(self.memory_space_id, "memory_space_id")?,
            task_type: self.task_type,
            status: self.status,
            request_digest: parse_identifier(self.request_digest, "request_digest")?,
            payload_json: self.payload_json,
            result_json: self.result_json,
            created_at: decode_time(self.created_at, "created_at")?,
            updated_at: decode_time(self.updated_at, "updated_at")?,
            expires_at: self
                .expires_at
                .map(|value| decode_time(value, "expires_at"))
                .transpose()?,
            lease_owner: self.lease_owner,
            lease_expires_at: self
                .lease_expires_at
                .map(|value| decode_time(value, "lease_expires_at"))
                .transpose()?,
            attempts: u32_from_sql(self.attempts, "attempts")?,
        })
    }
}

pub struct SqliteProjectionEventRepository<'connection> {
    connection: &'connection Connection,
}

impl ProjectionEventRepository for SqliteProjectionEventRepository<'_> {
    type Error = StorageError;

    fn add(&self, event: &ProjectionEventRecord) -> Result<(), Self::Error> {
        self.connection.execute(
            "INSERT INTO projection_events (
                projection_event_id, memory_space_id, aggregate_id, event_type,
                payload_json, occurred_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                event.projection_event_id.as_str(),
                event.memory_space_id.as_str(),
                event.aggregate_id,
                event.event_type,
                event.payload_json,
                encode_time(event.occurred_at)?,
            ],
        )?;
        Ok(())
    }

    fn list_for_memory_space(
        &self,
        memory_space_id: &MemorySpaceId,
    ) -> Result<Vec<ProjectionEventRecord>, Self::Error> {
        let mut statement = self.connection.prepare(
            "SELECT projection_event_id, memory_space_id, aggregate_id, event_type,
                    payload_json, occurred_at
             FROM projection_events
             WHERE memory_space_id = ?1
             ORDER BY occurred_at, projection_event_id",
        )?;
        let rows = statement.query_map([memory_space_id.as_str()], |row| {
            Ok(ProjectionEventRow {
                projection_event_id: row.get(0)?,
                memory_space_id: row.get(1)?,
                aggregate_id: row.get(2)?,
                event_type: row.get(3)?,
                payload_json: row.get(4)?,
                occurred_at: row.get(5)?,
            })
        })?;
        rows.map(|row| {
            row.map_err(StorageError::from)
                .and_then(ProjectionEventRow::into_domain)
        })
        .collect()
    }

    fn list_for_consumer(
        &self,
        memory_space_id: &MemorySpaceId,
        consumer_id: &str,
        after_event_id: Option<&ProjectionEventId>,
        limit: u32,
    ) -> Result<(Vec<ProjectionEventRecord>, bool), Self::Error> {
        if consumer_id.trim().is_empty() {
            return Err(StorageError::InvalidRecord(
                "projection consumer_id must not be empty".to_owned(),
            ));
        }
        if !(1..=1000).contains(&limit) {
            return Err(StorageError::InvalidRecord(
                "projection event limit must be between 1 and 1000".to_owned(),
            ));
        }
        let after = after_event_id
            .map(|event_id| {
                self.connection
                    .query_row(
                        "SELECT occurred_at FROM projection_events WHERE projection_event_id = ?1",
                        [event_id.as_str()],
                        |row| row.get::<_, String>(0),
                    )
                    .optional()
            })
            .transpose()?
            .flatten();
        let fetch_limit = i64::from(limit) + 1;
        let mut rows = Vec::new();
        let mut map_row = |row: &Row<'_>| {
            Ok(ProjectionEventRow {
                projection_event_id: row.get(0)?,
                memory_space_id: row.get(1)?,
                aggregate_id: row.get(2)?,
                event_type: row.get(3)?,
                payload_json: row.get(4)?,
                occurred_at: row.get(5)?,
            })
        };
        if let Some(after_occurred_at) = after {
            let mut statement = self.connection.prepare(
                "SELECT e.projection_event_id, e.memory_space_id, e.aggregate_id,
                        e.event_type, e.payload_json, e.occurred_at
                 FROM projection_events e
                 WHERE e.memory_space_id = ?1
                   AND (e.occurred_at > ?2 OR
                        (e.occurred_at = ?2 AND e.projection_event_id > ?3))
                   AND NOT EXISTS (
                       SELECT 1 FROM projection_event_acknowledgements a
                       WHERE a.projection_event_id = e.projection_event_id
                         AND a.consumer_id = ?4
                   )
                 ORDER BY e.occurred_at, e.projection_event_id
                 LIMIT ?5",
            )?;
            let mapped = statement.query_map(
                params![
                    memory_space_id.as_str(),
                    after_occurred_at,
                    after_event_id.expect("after event id exists").as_str(),
                    consumer_id,
                    fetch_limit,
                ],
                &mut map_row,
            )?;
            for row in mapped {
                rows.push(row?);
            }
        } else {
            let mut statement = self.connection.prepare(
                "SELECT e.projection_event_id, e.memory_space_id, e.aggregate_id,
                        e.event_type, e.payload_json, e.occurred_at
                 FROM projection_events e
                 WHERE e.memory_space_id = ?1
                   AND NOT EXISTS (
                       SELECT 1 FROM projection_event_acknowledgements a
                       WHERE a.projection_event_id = e.projection_event_id
                         AND a.consumer_id = ?2
                   )
                 ORDER BY e.occurred_at, e.projection_event_id
                 LIMIT ?3",
            )?;
            let mapped = statement.query_map(
                params![memory_space_id.as_str(), consumer_id, fetch_limit],
                &mut map_row,
            )?;
            for row in mapped {
                rows.push(row?);
            }
        }
        let has_more = rows.len() > limit as usize;
        rows.truncate(limit as usize);
        rows.into_iter()
            .map(ProjectionEventRow::into_domain)
            .collect::<Result<Vec<_>, _>>()
            .map(|events| (events, has_more))
    }

    fn acknowledge(
        &self,
        consumer_id: &str,
        event_ids: &[ProjectionEventId],
    ) -> Result<Vec<ProjectionEventId>, Self::Error> {
        if consumer_id.trim().is_empty() {
            return Err(StorageError::InvalidRecord(
                "projection consumer_id must not be empty".to_owned(),
            ));
        }
        let acknowledged_at = encode_time(OffsetDateTime::now_utc())?;
        let mut acknowledged = Vec::new();
        for event_id in event_ids {
            let exists = self
                .connection
                .query_row(
                    "SELECT 1 FROM projection_events WHERE projection_event_id = ?1",
                    [event_id.as_str()],
                    |_| Ok(()),
                )
                .optional()?;
            if exists.is_none() {
                return Err(StorageError::InvalidRecord(format!(
                    "projection event does not exist: {}",
                    event_id.as_str()
                )));
            }
            self.connection.execute(
                "INSERT OR IGNORE INTO projection_event_acknowledgements
                    (consumer_id, projection_event_id, acknowledged_at)
                 VALUES (?1, ?2, ?3)",
                params![consumer_id, event_id.as_str(), acknowledged_at],
            )?;
            acknowledged.push(event_id.clone());
        }
        Ok(acknowledged)
    }
}

struct ProjectionEventRow {
    projection_event_id: String,
    memory_space_id: String,
    aggregate_id: String,
    event_type: String,
    payload_json: String,
    occurred_at: String,
}

impl ProjectionEventRow {
    fn into_domain(self) -> Result<ProjectionEventRecord, StorageError> {
        Ok(ProjectionEventRecord {
            projection_event_id: parse_identifier(self.projection_event_id, "projection_event_id")?,
            memory_space_id: parse_identifier(self.memory_space_id, "memory_space_id")?,
            aggregate_id: self.aggregate_id,
            event_type: self.event_type,
            payload_json: self.payload_json,
            occurred_at: decode_time(self.occurred_at, "occurred_at")?,
        })
    }
}

pub struct SqliteContextUsageRepository<'connection> {
    connection: &'connection Connection,
}

impl ContextUsageRepository for SqliteContextUsageRepository<'_> {
    type Error = StorageError;

    fn add(&self, usage: &ContextUsageRecord) -> Result<(), Self::Error> {
        self.connection.execute(
            "INSERT INTO context_usage (
                usage_id, memory_space_id, knowledge_id, surface, metadata_json, used_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                usage.usage_id,
                usage.memory_space_id.as_str(),
                usage.knowledge_id.as_ref().map(ToString::to_string),
                usage.surface,
                usage.metadata_json,
                encode_time(usage.used_at)?,
            ],
        )?;
        Ok(())
    }

    fn list_for_memory_space(
        &self,
        memory_space_id: &MemorySpaceId,
    ) -> Result<Vec<ContextUsageRecord>, Self::Error> {
        let mut statement = self.connection.prepare(
            "SELECT usage_id, memory_space_id, knowledge_id, surface, metadata_json, used_at
             FROM context_usage
             WHERE memory_space_id = ?1
             ORDER BY used_at, usage_id",
        )?;
        let rows = statement.query_map([memory_space_id.as_str()], |row| {
            Ok(ContextUsageRow {
                usage_id: row.get(0)?,
                memory_space_id: row.get(1)?,
                knowledge_id: row.get(2)?,
                surface: row.get(3)?,
                metadata_json: row.get(4)?,
                used_at: row.get(5)?,
            })
        })?;
        rows.map(|row| {
            row.map_err(StorageError::from)
                .and_then(ContextUsageRow::into_domain)
        })
        .collect()
    }
}

struct ContextUsageRow {
    usage_id: String,
    memory_space_id: String,
    knowledge_id: Option<String>,
    surface: String,
    metadata_json: String,
    used_at: String,
}

impl ContextUsageRow {
    fn into_domain(self) -> Result<ContextUsageRecord, StorageError> {
        Ok(ContextUsageRecord {
            usage_id: self.usage_id,
            memory_space_id: parse_identifier(self.memory_space_id, "memory_space_id")?,
            knowledge_id: self
                .knowledge_id
                .map(|value| parse_identifier(value, "knowledge_id"))
                .transpose()?,
            surface: self.surface,
            metadata_json: self.metadata_json,
            used_at: decode_time(self.used_at, "used_at")?,
        })
    }
}

fn encode_time(value: OffsetDateTime) -> Result<String, StorageError> {
    value
        .format(&Rfc3339)
        .map_err(|error| StorageError::Timestamp(error.to_string()))
}

fn encode_optional_time(value: Option<OffsetDateTime>) -> Result<Option<String>, StorageError> {
    value.map(encode_time).transpose()
}

fn decode_time(value: String, field: &str) -> Result<OffsetDateTime, StorageError> {
    OffsetDateTime::parse(&value, &Rfc3339)
        .map_err(|error| StorageError::InvalidRecord(format!("{field}: {error}")))
}

fn parse_identifier<T>(value: String, field: &str) -> Result<T, StorageError>
where
    T: TryFrom<String>,
    T::Error: Display,
{
    T::try_from(value).map_err(|error| StorageError::InvalidRecord(format!("{field}: {error}")))
}

fn decode_json<T>(value: &str, field: &str) -> Result<T, StorageError>
where
    T: serde::de::DeserializeOwned,
{
    serde_json::from_str(value)
        .map_err(|error| StorageError::InvalidRecord(format!("{field}: {error}")))
}

fn parse_evidence_relation(value: &str) -> Result<EvidenceRelation, StorageError> {
    match value {
        "origin" => Ok(EvidenceRelation::Origin),
        "supports" => Ok(EvidenceRelation::Supports),
        "contradicts" => Ok(EvidenceRelation::Contradicts),
        "refines" => Ok(EvidenceRelation::Refines),
        value => Err(StorageError::InvalidRecord(format!(
            "unknown evidence relation {value}"
        ))),
    }
}

fn sql_u64(value: u64, field: &str) -> Result<i64, StorageError> {
    i64::try_from(value)
        .map_err(|_| StorageError::InvalidRecord(format!("{field} exceeds SQLite integer range")))
}

fn u64_from_sql(value: i64, field: &str) -> Result<u64, StorageError> {
    u64::try_from(value).map_err(|_| StorageError::InvalidRecord(format!("{field} is negative")))
}

fn u32_from_sql(value: i64, field: &str) -> Result<u32, StorageError> {
    u32::try_from(value)
        .map_err(|_| StorageError::InvalidRecord(format!("{field} is outside u32 range")))
}
