use std::collections::{BTreeMap, BTreeSet, HashMap};

use ledgermind_application::{
    AcceptHypothesisCommand, AcceptHypothesisResult, AckProjectionEventsCommand,
    ContextUsageRecord, ContextUsageRepository, ContextView, CoreService, EvidenceRepository,
    HypothesisRepository, IdempotencyRepository, KnowledgeRepository, KnowledgeSearch,
    ModelTaskPage, ModelTaskRecord, ModelTaskRepository, PollModelTasksRequest,
    PollProjectionEventsRequest, ProjectionEventPage, ProjectionEventRecord,
    ProjectionEventRepository, RecordContextUsageCommand, RetrieveContextRequest,
    RevisionRepository, StoredIdempotencyResult, SubmitModelResult, SubmitModelResultCommand,
};
use ledgermind_domain::{
    EvidenceLink, EvidenceRelation, KnowledgeId, KnowledgeInput, KnowledgeItem, KnowledgeRevision,
    MergeProposal, Phase, ProjectionEventId, RevisionId,
};
use rusqlite::{Connection, params};
use serde::Deserialize;
use serde_json::{Value, json};
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use uuid::Uuid;

use crate::{Database, SqliteRepositories, StorageError};

pub struct SqliteCoreService {
    database: Database,
}

impl SqliteCoreService {
    pub fn open_in_memory() -> Result<Self, StorageError> {
        let mut database = Database::open_in_memory()?;
        database.migrate()?;
        database.verify_core_schema()?;
        Ok(Self { database })
    }

    pub fn open(path: impl AsRef<std::path::Path>) -> Result<Self, StorageError> {
        let mut database = Database::open(path)?;
        database.migrate()?;
        database.verify_core_schema()?;
        Ok(Self { database })
    }

    pub fn database(&self) -> &Database {
        &self.database
    }

    pub fn database_mut(&mut self) -> &mut Database {
        &mut self.database
    }

    pub fn health(&self) -> Result<(), StorageError> {
        self.database.verify_core_schema()
    }

    pub fn enqueue_model_task(&mut self, task: &ModelTaskRecord) -> Result<(), StorageError> {
        let mut unit_of_work = self.database.unit_of_work();
        unit_of_work.transaction(|repositories| {
            ensure_memory_space(
                repositories.connection(),
                &task.memory_space_id,
                task.created_at,
            )?;
            repositories.model_tasks().add(task)
        })
    }
}

impl CoreService for SqliteCoreService {
    type Error = StorageError;

    fn accept_hypothesis(
        &mut self,
        command: &AcceptHypothesisCommand,
    ) -> Result<AcceptHypothesisResult, Self::Error> {
        if command.hypothesis.memory_space_id() != &command.memory_space_id {
            return Err(StorageError::InvalidRecord(
                "hypothesis memory space does not match command".to_owned(),
            ));
        }
        let now = OffsetDateTime::now_utc();
        let mut unit_of_work = self.database.unit_of_work();
        unit_of_work.transaction(|repositories| {
            ensure_memory_space(repositories.connection(), &command.memory_space_id, now)?;
            if let Some(previous) = repositories
                .idempotency()
                .get(&command.memory_space_id, &command.idempotency_key)?
            {
                if previous.request_hash != command.request_hash {
                    return Err(StorageError::IdempotencyConflict {
                        memory_space_id: command.memory_space_id.to_string(),
                        key: command.idempotency_key.to_string(),
                    });
                }
                let mut result: AcceptHypothesisResult =
                    serde_json::from_str(&previous.response_json)?;
                result.duplicate = true;
                return Ok(result);
            }

            repositories.hypotheses().add(&command.hypothesis)?;
            let knowledge_id = KnowledgeId::from_uuid(Uuid::new_v4());
            let knowledge = KnowledgeItem::new(KnowledgeInput {
                knowledge_id: knowledge_id.clone(),
                memory_space_id: command.memory_space_id.clone(),
                title: command.hypothesis.title().to_owned(),
                target: command.hypothesis.target().to_owned(),
                statement: command.hypothesis.statement().to_owned(),
                rationale: command.hypothesis.rationale().to_owned(),
                phase: Phase::Pattern,
                version: 1,
                created_at: now,
                updated_at: now,
                superseded_by_id: None,
                deleted_at: None,
            })?;
            repositories.knowledge().add(&knowledge)?;

            let revision = KnowledgeRevision::from_snapshot(
                RevisionId::from_uuid(Uuid::new_v4()),
                knowledge_id.clone(),
                1,
                "accepted_hypothesis".to_owned(),
                json!({
                    "knowledge_id": knowledge_id.as_str(),
                    "memory_space_id": command.memory_space_id.as_str(),
                    "title": knowledge.title(),
                    "target": knowledge.target(),
                    "statement": knowledge.statement(),
                    "rationale": knowledge.rationale(),
                    "phase": Phase::Pattern.as_str(),
                    "version": 1,
                }),
                Some(command.hypothesis.id().clone()),
                now,
            )?;
            repositories.revisions().add(&revision)?;
            repositories.evidence().add(&EvidenceLink::new(
                knowledge_id.clone(),
                command.hypothesis.id().clone(),
                EvidenceRelation::Origin,
                now,
            ))?;

            let result = AcceptHypothesisResult {
                accepted: true,
                duplicate: false,
                core_reference_id: Some(knowledge_id.clone()),
                result_json: None,
            };
            let response_json = serde_json::to_string(&result)?;
            repositories.projection_events().add(
                &ledgermind_application::ProjectionEventRecord {
                    projection_event_id: ProjectionEventId::from_uuid(Uuid::new_v4()),
                    memory_space_id: command.memory_space_id.clone(),
                    aggregate_id: knowledge_id.to_string(),
                    event_type: "knowledge_projection_upsert".to_owned(),
                    payload_json: serde_json::to_string(&json!({
                        "knowledge_id": knowledge_id,
                        "memory_space_id": command.memory_space_id,
                        "title": knowledge.title(),
                        "target": knowledge.target(),
                        "statement": knowledge.statement(),
                        "projection_version": 1,
                    }))?,
                    occurred_at: now,
                },
            )?;
            repositories.idempotency().put(&StoredIdempotencyResult {
                memory_space_id: command.memory_space_id.clone(),
                idempotency_key: command.idempotency_key.clone(),
                request_hash: command.request_hash.clone(),
                response_json,
                created_at: now,
                expires_at: None,
            })?;
            Ok(result)
        })
    }

    fn retrieve_context(
        &self,
        request: &RetrieveContextRequest,
    ) -> Result<ContextView, Self::Error> {
        let repositories = SqliteRepositories::new(self.database.connection());
        if !request.candidate_ids.is_empty() {
            let scores: HashMap<_, _> = request.candidate_scores.iter().cloned().collect();
            let mut items = Vec::new();
            for knowledge_id in &request.candidate_ids {
                let Some(knowledge) = repositories
                    .knowledge()
                    .get(&request.memory_space_id, knowledge_id)?
                else {
                    continue;
                };
                if !knowledge.is_current() {
                    continue;
                }
                items.push(ledgermind_application::KnowledgeSearchHit {
                    knowledge_id: knowledge.id().clone(),
                    title: knowledge.title().to_owned(),
                    target: knowledge.target().to_owned(),
                    statement: knowledge.statement().to_owned(),
                    relevance: scores.get(knowledge_id).copied().unwrap_or(0.0),
                });
            }
            items.sort_by(|left, right| {
                right
                    .relevance
                    .total_cmp(&left.relevance)
                    .then_with(|| left.knowledge_id.cmp(&right.knowledge_id))
            });
            items.truncate(request.limit as usize);
            return Ok(ContextView { items });
        }
        Ok(ContextView {
            items: repositories.knowledge().search(
                &request.memory_space_id,
                &request.query,
                request.limit,
            )?,
        })
    }

    fn record_context_usage(
        &mut self,
        command: &RecordContextUsageCommand,
    ) -> Result<(), Self::Error> {
        let now = command.used_at;
        let mut unit_of_work = self.database.unit_of_work();
        unit_of_work.transaction(|repositories| {
            ensure_memory_space(repositories.connection(), &command.memory_space_id, now)?;
            let metadata_json = serde_json::to_string(&json!({
                "session_id": command.session_id,
                "round_id": command.round_id,
            }))?;
            if command.item_ids.is_empty() {
                repositories.context_usage().add(&ContextUsageRecord {
                    usage_id: command.usage_id.clone(),
                    memory_space_id: command.memory_space_id.clone(),
                    knowledge_id: None,
                    surface: "retrieve_context".to_owned(),
                    metadata_json,
                    used_at: now,
                })?;
                return Ok(());
            }
            for (index, knowledge_id) in command.item_ids.iter().enumerate() {
                if repositories
                    .knowledge()
                    .get(&command.memory_space_id, knowledge_id)?
                    .is_none()
                {
                    return Err(StorageError::NotFound(format!(
                        "knowledge item {} in memory space {}",
                        knowledge_id, command.memory_space_id
                    )));
                }
                repositories.context_usage().add(&ContextUsageRecord {
                    usage_id: format!("{}:{index}", command.usage_id),
                    memory_space_id: command.memory_space_id.clone(),
                    knowledge_id: Some(knowledge_id.clone()),
                    surface: "retrieve_context".to_owned(),
                    metadata_json: metadata_json.clone(),
                    used_at: now,
                })?;
            }
            Ok(())
        })
    }

    fn poll_projection_events(
        &self,
        request: &PollProjectionEventsRequest,
    ) -> Result<ProjectionEventPage, Self::Error> {
        let repositories = SqliteRepositories::new(self.database.connection());
        let (events, has_more) = repositories.projection_events().list_for_consumer(
            &request.memory_space_id,
            &request.consumer_id,
            request.after_event_id.as_ref(),
            request.limit,
        )?;
        Ok(ProjectionEventPage { events, has_more })
    }

    fn ack_projection_events(
        &mut self,
        command: &AckProjectionEventsCommand,
    ) -> Result<Vec<ledgermind_domain::ProjectionEventId>, Self::Error> {
        let mut unit_of_work = self.database.unit_of_work();
        unit_of_work.transaction(|repositories| {
            repositories
                .projection_events()
                .acknowledge(&command.consumer_id, &command.event_ids)
        })
    }

    fn poll_model_tasks(
        &mut self,
        request: &PollModelTasksRequest,
    ) -> Result<ModelTaskPage, Self::Error> {
        if request.worker_id.trim().is_empty()
            || !(1..=100).contains(&request.limit)
            || !(1..=3600).contains(&request.lease_seconds)
        {
            return Err(StorageError::InvalidRecord(
                "model task poll request is invalid".to_owned(),
            ));
        }
        let mut unit_of_work = self.database.unit_of_work();
        unit_of_work.transaction(|repositories| {
            let (tasks, has_more) = repositories.model_tasks().claim_for_worker(
                &request.memory_space_id,
                &request.worker_id,
                OffsetDateTime::now_utc(),
                time::Duration::seconds(request.lease_seconds as i64),
                request.limit,
            )?;
            Ok(ModelTaskPage { tasks, has_more })
        })
    }

    fn submit_model_result(
        &mut self,
        command: &SubmitModelResultCommand,
    ) -> Result<SubmitModelResult, Self::Error> {
        let result: Value = serde_json::from_str(&command.result_json)?;
        if !result.is_object() {
            return Err(StorageError::InvalidRecord(
                "model result must be a JSON object".to_owned(),
            ));
        }
        let now = OffsetDateTime::now_utc();
        let mut unit_of_work = self.database.unit_of_work();
        unit_of_work.transaction(|repositories| {
            let task = repositories
                .model_tasks()
                .get(&command.memory_space_id, &command.task_id)?
                .ok_or_else(|| StorageError::NotFound(format!("model task {}", command.task_id)))?;
            if task.status == "completed" {
                return repositories.model_tasks().submit_result(
                    &command.memory_space_id,
                    &command.task_id,
                    &command.worker_id,
                    command.result_json.clone(),
                    now,
                );
            }
            if task.status != "leased"
                || task.lease_owner.as_deref() != Some(command.worker_id.as_str())
                || task
                    .lease_expires_at
                    .is_none_or(|lease_expires_at| lease_expires_at <= now)
                || task.expires_at.is_some_and(|expires_at| expires_at <= now)
            {
                return repositories.model_tasks().submit_result(
                    &command.memory_space_id,
                    &command.task_id,
                    &command.worker_id,
                    command.result_json.clone(),
                    now,
                );
            }
            let validated = validate_merge_result(repositories, &task, &command.result_json)?;
            apply_merge_proposal(
                repositories,
                &task,
                &validated.proposal,
                &validated.expected_versions,
                now,
            )?;
            repositories.model_tasks().submit_result(
                &command.memory_space_id,
                &command.task_id,
                &command.worker_id,
                command.result_json.clone(),
                now,
            )
        })
    }
}

struct ValidatedMergeResult {
    proposal: MergeProposal,
    expected_versions: BTreeMap<String, u64>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredMergeTaskPayload {
    task_id: String,
    operation: String,
    memory_space_id: String,
    expected_versions: BTreeMap<String, u64>,
    expires_at: String,
    model_input: Value,
    #[serde(default)]
    lease_expires_at: Option<String>,
}

fn validate_merge_result(
    repositories: &SqliteRepositories<'_>,
    task: &ModelTaskRecord,
    result_json: &str,
) -> Result<ValidatedMergeResult, StorageError> {
    if task.task_type != "merge_knowledge" {
        return Err(StorageError::InvalidRecord(format!(
            "unsupported model task type {}",
            task.task_type
        )));
    }
    let payload: StoredMergeTaskPayload =
        serde_json::from_str(&task.payload_json).map_err(|error| {
            StorageError::InvalidRecord(format!("invalid merge task payload: {error}"))
        })?;
    if payload.task_id != task.task_id.to_string()
        || payload.operation != task.task_type
        || payload.memory_space_id != task.memory_space_id.to_string()
    {
        return Err(StorageError::InvalidRecord(
            "stored merge task metadata does not match task record".to_owned(),
        ));
    }
    if payload.expected_versions.len() < 2 {
        return Err(StorageError::InvalidRecord(
            "merge task requires at least two expected versions".to_owned(),
        ));
    }
    let payload_expires_at =
        OffsetDateTime::parse(&payload.expires_at, &Rfc3339).map_err(|error| {
            StorageError::InvalidRecord(format!("invalid merge task expires_at: {error}"))
        })?;
    if task.expires_at != Some(payload_expires_at) {
        return Err(StorageError::InvalidRecord(
            "merge task expiry does not match task record".to_owned(),
        ));
    }
    if let Some(lease_expires_at) = payload.lease_expires_at {
        OffsetDateTime::parse(&lease_expires_at, &Rfc3339).map_err(|error| {
            StorageError::InvalidRecord(format!("invalid merge task lease_expires_at: {error}"))
        })?;
    }

    let required_constraints =
        validate_model_input(&payload.model_input, &payload.expected_versions)?;
    let proposal: MergeProposal = serde_json::from_str(result_json).map_err(|error| {
        StorageError::InvalidRecord(format!("merge result failed domain validation: {error}"))
    })?;
    validate_proposal_references(&proposal, &payload.expected_versions)?;
    validate_proposal_constraints(&proposal, &required_constraints)?;

    for (raw_knowledge_id, expected_version) in &payload.expected_versions {
        let knowledge_id = KnowledgeId::try_from(raw_knowledge_id.clone()).map_err(|error| {
            StorageError::InvalidRecord(format!("invalid merge knowledge reference: {error}"))
        })?;
        let knowledge = repositories
            .knowledge()
            .get(&task.memory_space_id, &knowledge_id)?
            .ok_or_else(|| StorageError::NotFound(format!("knowledge item {knowledge_id}")))?;
        if !knowledge.is_current() {
            return Err(StorageError::InvalidRecord(format!(
                "knowledge item {knowledge_id} is not current"
            )));
        }
        if knowledge.version() != *expected_version {
            return Err(StorageError::VersionConflict {
                knowledge_id: knowledge_id.to_string(),
                expected: *expected_version,
                actual: knowledge.version(),
            });
        }
    }
    Ok(ValidatedMergeResult {
        proposal,
        expected_versions: payload.expected_versions,
    })
}

fn validate_model_input(
    model_input: &Value,
    expected_versions: &BTreeMap<String, u64>,
) -> Result<BTreeSet<String>, StorageError> {
    let items = model_input
        .get("items")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            StorageError::InvalidRecord("merge model_input.items is required".to_owned())
        })?;
    let expected_references: BTreeSet<&str> =
        expected_versions.keys().map(String::as_str).collect();
    let mut actual_references = BTreeSet::new();
    let mut required_constraints = BTreeSet::new();
    for item in items {
        let object = item.as_object().ok_or_else(|| {
            StorageError::InvalidRecord("merge model_input.items must contain objects".to_owned())
        })?;
        let reference = object
            .get("reference")
            .and_then(Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| {
                StorageError::InvalidRecord(
                    "merge model_input item reference is required".to_owned(),
                )
            })?;
        if !actual_references.insert(reference.to_owned()) {
            return Err(StorageError::InvalidRecord(
                "merge model_input references must be unique".to_owned(),
            ));
        }
        if !expected_references.contains(reference) {
            return Err(StorageError::InvalidRecord(format!(
                "merge model_input contains unexpected reference {reference}"
            )));
        }
        if let Some(constraints) = object.get("required_constraints") {
            for constraint in constraints.as_array().ok_or_else(|| {
                StorageError::InvalidRecord(
                    "merge required_constraints must be an array".to_owned(),
                )
            })? {
                let value = constraint
                    .as_str()
                    .filter(|value| !value.trim().is_empty())
                    .ok_or_else(|| {
                        StorageError::InvalidRecord(
                            "merge required constraints must be non-empty strings".to_owned(),
                        )
                    })?;
                required_constraints.insert(value.to_owned());
            }
        }
    }
    if actual_references
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>()
        != expected_references
    {
        return Err(StorageError::InvalidRecord(
            "merge model_input references do not match expected versions".to_owned(),
        ));
    }
    Ok(required_constraints)
}

fn validate_proposal_references(
    proposal: &MergeProposal,
    expected_versions: &BTreeMap<String, u64>,
) -> Result<(), StorageError> {
    let expected: BTreeSet<&str> = expected_versions.keys().map(String::as_str).collect();
    let actual: BTreeSet<&str> = proposal
        .preserved_references()
        .iter()
        .map(KnowledgeId::as_str)
        .collect();
    if actual.len() != proposal.preserved_references().len() || actual != expected {
        return Err(StorageError::InvalidRecord(
            "merge result preserved_references must exactly match expected versions".to_owned(),
        ));
    }
    Ok(())
}

fn validate_proposal_constraints(
    proposal: &MergeProposal,
    required_constraints: &BTreeSet<String>,
) -> Result<(), StorageError> {
    let actual: BTreeSet<&str> = proposal
        .preserved_constraints()
        .iter()
        .map(String::as_str)
        .collect();
    let required: BTreeSet<&str> = required_constraints.iter().map(String::as_str).collect();
    if actual.len() != proposal.preserved_constraints().len() || actual != required {
        return Err(StorageError::InvalidRecord(
            "merge result preserved_constraints must exactly match task constraints".to_owned(),
        ));
    }
    Ok(())
}

fn apply_merge_proposal(
    repositories: &SqliteRepositories<'_>,
    task: &ModelTaskRecord,
    proposal: &MergeProposal,
    expected_versions: &BTreeMap<String, u64>,
    now: OffsetDateTime,
) -> Result<KnowledgeId, StorageError> {
    let successor_id = KnowledgeId::from_uuid(Uuid::new_v4());
    let successor = KnowledgeItem::new(KnowledgeInput {
        knowledge_id: successor_id.clone(),
        memory_space_id: task.memory_space_id.clone(),
        title: proposal.title().to_owned(),
        target: proposal.target().to_owned(),
        statement: proposal.statement().to_owned(),
        rationale: proposal.rationale().to_owned(),
        phase: Phase::Emergent,
        version: 1,
        created_at: now,
        updated_at: now,
        superseded_by_id: None,
        deleted_at: None,
    })?;
    repositories.knowledge().add(&successor)?;
    repositories
        .revisions()
        .add(&KnowledgeRevision::from_snapshot(
            RevisionId::from_uuid(Uuid::new_v4()),
            successor_id.clone(),
            successor.version(),
            "model_merge_created".to_owned(),
            json!({
                "knowledge_id": successor.id().as_str(),
                "memory_space_id": successor.memory_space_id().as_str(),
                "title": successor.title(),
                "target": successor.target(),
                "statement": successor.statement(),
                "rationale": successor.rationale(),
                "phase": successor.phase().as_str(),
                "version": successor.version(),
                "source_knowledge_ids": proposal
                    .preserved_references()
                    .iter()
                    .map(KnowledgeId::as_str)
                    .collect::<Vec<_>>(),
                "preserved_constraints": proposal.preserved_constraints(),
            }),
            None,
            now,
        )?)?;

    for (raw_knowledge_id, expected_version) in expected_versions {
        let knowledge_id = KnowledgeId::try_from(raw_knowledge_id.clone()).map_err(|error| {
            StorageError::InvalidRecord(format!("invalid merge knowledge reference: {error}"))
        })?;
        let source = repositories
            .knowledge()
            .get(&task.memory_space_id, &knowledge_id)?
            .ok_or_else(|| StorageError::NotFound(format!("knowledge item {knowledge_id}")))?;
        if !source.is_current() {
            return Err(StorageError::InvalidRecord(format!(
                "knowledge item {knowledge_id} is not current"
            )));
        }
        if source.version() != *expected_version {
            return Err(StorageError::VersionConflict {
                knowledge_id: knowledge_id.to_string(),
                expected: *expected_version,
                actual: source.version(),
            });
        }
        let superseded = source.with_superseded_by(successor_id.clone(), now)?;
        repositories
            .knowledge()
            .update(&superseded, source.version())?;
        repositories
            .revisions()
            .add(&KnowledgeRevision::from_snapshot(
                RevisionId::from_uuid(Uuid::new_v4()),
                superseded.id().clone(),
                superseded.version(),
                "model_merge_superseded".to_owned(),
                knowledge_snapshot(&superseded)?,
                None,
                now,
            )?)?;
        repositories.connection().execute(
            "INSERT INTO supersession_links(
                predecessor_knowledge_id, successor_knowledge_id, created_at
             ) VALUES (?, ?, ?)",
            params![
                superseded.id().as_str(),
                successor.id().as_str(),
                encode_timestamp(now)?,
            ],
        )?;
        add_projection_delete_event(repositories, &superseded, now)?;
    }
    add_projection_upsert_event(repositories, &successor, now)?;
    Ok(successor_id)
}

fn knowledge_snapshot(item: &KnowledgeItem) -> Result<Value, StorageError> {
    Ok(json!({
        "knowledge_id": item.id().as_str(),
        "memory_space_id": item.memory_space_id().as_str(),
        "title": item.title(),
        "target": item.target(),
        "statement": item.statement(),
        "rationale": item.rationale(),
        "phase": item.phase().as_str(),
        "version": item.version(),
        "created_at": encode_timestamp(item.created_at())?,
        "updated_at": encode_timestamp(item.updated_at())?,
        "superseded_by_id": item.superseded_by_id().map(ToString::to_string),
        "deleted_at": item.deleted_at().map(encode_timestamp).transpose()?,
    }))
}

fn add_projection_delete_event(
    repositories: &SqliteRepositories<'_>,
    item: &KnowledgeItem,
    now: OffsetDateTime,
) -> Result<(), StorageError> {
    repositories
        .projection_events()
        .add(&ProjectionEventRecord {
            projection_event_id: ProjectionEventId::from_uuid(Uuid::new_v4()),
            memory_space_id: item.memory_space_id().clone(),
            aggregate_id: item.id().to_string(),
            event_type: "knowledge_projection_delete".to_owned(),
            payload_json: serde_json::to_string(&json!({
                "knowledge_id": item.id().as_str(),
                "memory_space_id": item.memory_space_id().as_str(),
                "projection_version": item.version(),
            }))?,
            occurred_at: now,
        })
}

fn add_projection_upsert_event(
    repositories: &SqliteRepositories<'_>,
    item: &KnowledgeItem,
    now: OffsetDateTime,
) -> Result<(), StorageError> {
    repositories
        .projection_events()
        .add(&ProjectionEventRecord {
            projection_event_id: ProjectionEventId::from_uuid(Uuid::new_v4()),
            memory_space_id: item.memory_space_id().clone(),
            aggregate_id: item.id().to_string(),
            event_type: "knowledge_projection_upsert".to_owned(),
            payload_json: serde_json::to_string(&json!({
                "knowledge_id": item.id().as_str(),
                "memory_space_id": item.memory_space_id().as_str(),
                "title": item.title(),
                "target": item.target(),
                "statement": item.statement(),
                "projection_version": item.version(),
            }))?,
            occurred_at: now,
        })
}

fn encode_timestamp(value: OffsetDateTime) -> Result<String, StorageError> {
    value
        .format(&Rfc3339)
        .map_err(|error| StorageError::Timestamp(error.to_string()))
}

fn ensure_memory_space(
    connection: &Connection,
    memory_space_id: &ledgermind_domain::MemorySpaceId,
    now: OffsetDateTime,
) -> Result<(), StorageError> {
    let created_at = now
        .format(&Rfc3339)
        .map_err(|error| StorageError::Timestamp(error.to_string()))?;
    connection.execute(
        "INSERT OR IGNORE INTO memory_spaces
            (memory_space_id, display_name, source_client, created_at, updated_at)
         VALUES (?1, ?2, 'ledgermind-local', ?3, ?3)",
        params![
            memory_space_id.as_str(),
            memory_space_id.as_str(),
            created_at
        ],
    )?;
    Ok(())
}
