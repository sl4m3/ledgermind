mod framing;

use std::{env, io, path::Path};

use ledgermind_application::{
    AcceptHypothesisCommand, AckProjectionEventsCommand, ContextView, CoreService,
    PollModelTasksRequest, PollProjectionEventsRequest, RecordContextUsageCommand,
    RetrieveContextRequest, SubmitModelResultCommand,
};
use ledgermind_domain::{MemorySpaceId, ModelTaskId, ProjectionEventId};
use ledgermind_protocol::{
    AcceptHypothesisPayload, AcceptHypothesisResultPayload, AckProjectionEventsPayload,
    AckProjectionEventsResultPayload, CORE_IPC_PROTOCOL_VERSION, ContextViewItemPayload,
    ContextViewPayload, CoreError, CoreErrorCode, CoreRequestEnvelope, CoreResponseEnvelope,
    HandshakePayload, HealthResult, ModelTaskPayload, Operation, PollModelTasksPayload,
    PollModelTasksResultPayload, PollProjectionEventsPayload, PollProjectionEventsResultPayload,
    ProjectionEventPayload, ProtocolError, RecordContextUsagePayload,
    RecordContextUsageResultPayload, RetrieveContextPayload, ShutdownResultPayload,
    SubmitModelResultPayload, SubmitModelResultResultPayload,
};
use ledgermind_storage_sqlite::{SqliteCoreService, StorageError};
use serde::de::DeserializeOwned;
use serde_json::{Value, json};
use thiserror::Error;
use time::OffsetDateTime;
use uuid::Uuid;

pub use framing::{FrameError, MAX_FRAME_BYTES, read_frame, write_frame};

#[derive(Debug, Error)]
pub enum DaemonError {
    #[error("daemon I/O failed: {0}")]
    Io(#[from] io::Error),

    #[error("daemon frame failed: {0}")]
    Frame(#[from] FrameError),

    #[error("daemon storage failed: {0}")]
    Storage(#[from] StorageError),

    #[error("daemon protocol failed: {0}")]
    Protocol(#[from] ProtocolError),

    #[error("daemon JSON failed: {0}")]
    Json(#[from] serde_json::Error),
}

#[derive(Debug)]
pub struct DispatchOutcome {
    pub response: CoreResponseEnvelope,
    pub stop: bool,
}

pub fn dispatch(
    request: CoreRequestEnvelope,
    service: &mut SqliteCoreService,
) -> Result<DispatchOutcome, DaemonError> {
    let request_id = request.request_id.clone();
    let response = match request.operation {
        Operation::Handshake => handle_handshake(request.payload, &request_id),
        Operation::Health => handle_health(service, &request_id),
        Operation::AcceptHypothesis => handle_accept(service, request.payload, &request_id),
        Operation::RetrieveContext => handle_retrieve(service, request.payload, &request_id),
        Operation::RecordContextUsage => handle_record_usage(service, request.payload, &request_id),
        Operation::PollProjectionEvents => {
            handle_poll_projection_events(service, request.payload, &request_id)
        }
        Operation::AckProjectionEvents => {
            handle_ack_projection_events(service, request.payload, &request_id)
        }
        Operation::PollModelTasks => handle_poll_model_tasks(service, request.payload, &request_id),
        Operation::SubmitModelResult => {
            handle_submit_model_result(service, request.payload, &request_id)
        }
        Operation::Shutdown => Ok((
            CoreResponseEnvelope::ok(
                &request_id,
                serde_json::to_value(ShutdownResultPayload { stopped: true })?,
            )?,
            true,
        )),
    }?;
    Ok(DispatchOutcome {
        response: response.0,
        stop: response.1,
    })
}

pub fn run_stdio(path: impl AsRef<Path>) -> Result<(), DaemonError> {
    let mut service = SqliteCoreService::open(path)?;
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut input = stdin.lock();
    let mut output = stdout.lock();
    loop {
        let Some(payload) = read_frame(&mut input)? else {
            return Ok(());
        };
        let request =
            match CoreRequestEnvelope::from_json(std::str::from_utf8(&payload).map_err(
                |error| ProtocolError::Invalid(format!("request is not UTF-8: {error}")),
            )?) {
                Ok(request) => request,
                Err(error) => {
                    eprintln!("core request rejected: {error}");
                    continue;
                }
            };
        let outcome = dispatch(request, &mut service)?;
        write_frame(&mut output, outcome.response.to_json().as_bytes())?;
        if outcome.stop {
            return Ok(());
        }
    }
}

fn handle_handshake(
    payload: Value,
    request_id: &str,
) -> Result<(CoreResponseEnvelope, bool), DaemonError> {
    let payload: HandshakePayload = parse_payload(payload)?;
    payload.validate()?;
    let result = json!({
        "protocol_version": CORE_IPC_PROTOCOL_VERSION,
        "server_name": "ledgermind-rust-core",
        "version": env!("CARGO_PKG_VERSION"),
        "operations": [
            "handshake",
            "health",
            "accept_hypothesis",
            "retrieve_context",
            "record_context_usage",
            "poll_projection_events",
            "ack_projection_events",
            "shutdown"
        ]
    });
    Ok((CoreResponseEnvelope::ok(request_id, result)?, false))
}

fn handle_health(
    service: &SqliteCoreService,
    request_id: &str,
) -> Result<(CoreResponseEnvelope, bool), DaemonError> {
    match service
        .health()
        .and_then(|()| service.database().schema_version())
    {
        Ok(schema_version) => Ok((
            CoreResponseEnvelope::ok(
                request_id,
                serde_json::to_value(HealthResult {
                    healthy: true,
                    backend: "rust".to_owned(),
                    detail: None,
                    protocol_version: CORE_IPC_PROTOCOL_VERSION,
                    schema_version,
                    environment_keys: core_environment_keys(),
                })?,
            )?,
            false,
        )),
        Err(error) => Ok((
            error_response(request_id, map_storage_error(&error, false))?,
            false,
        )),
    }
}

fn core_environment_keys() -> Vec<String> {
    let mut keys: Vec<String> = env::vars().map(|(key, _)| key).collect();
    keys.sort();
    keys
}

fn handle_accept(
    service: &mut SqliteCoreService,
    payload: Value,
    request_id: &str,
) -> Result<(CoreResponseEnvelope, bool), DaemonError> {
    let payload: AcceptHypothesisPayload = match parse_payload(payload) {
        Ok(payload) => payload,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, true))?,
                false,
            ));
        }
    };
    let input = match payload.into_domain() {
        Ok(input) => input,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, true))?,
                false,
            ));
        }
    };
    let command = AcceptHypothesisCommand {
        command_id: input.command_id,
        idempotency_key: input.idempotency_key,
        request_hash: input.request_hash,
        memory_space_id: input.memory_space_id,
        hypothesis: input.hypothesis,
    };
    match service.accept_hypothesis(&command) {
        Ok(result) => Ok((
            CoreResponseEnvelope::ok(
                request_id,
                serde_json::to_value(AcceptHypothesisResultPayload {
                    accepted: result.accepted,
                    duplicate: result.duplicate,
                    core_reference_id: result.core_reference_id.map(|value| value.to_string()),
                    result_json: result.result_json,
                })?,
            )?,
            false,
        )),
        Err(error) => Ok((
            error_response(request_id, map_storage_error(&error, true))?,
            false,
        )),
    }
}

fn handle_retrieve(
    service: &mut SqliteCoreService,
    payload: Value,
    request_id: &str,
) -> Result<(CoreResponseEnvelope, bool), DaemonError> {
    let payload: RetrieveContextPayload = match parse_payload(payload) {
        Ok(payload) => payload,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, false))?,
                false,
            ));
        }
    };
    let input = match payload.into_domain() {
        Ok(input) => input,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, false))?,
                false,
            ));
        }
    };
    match service.retrieve_context(&RetrieveContextRequest {
        memory_space_id: input.memory_space_id,
        query: input.query,
        limit: input.limit,
        candidate_ids: input.candidate_ids,
        candidate_scores: input.candidate_scores,
    }) {
        Ok(ContextView { items }) => Ok((
            CoreResponseEnvelope::ok(
                request_id,
                serde_json::to_value(ContextViewPayload {
                    api_version: "1".to_owned(),
                    items: items
                        .into_iter()
                        .map(|item| ContextViewItemPayload {
                            knowledge_id: item.knowledge_id.to_string(),
                            title: item.title,
                            target: item.target,
                            statement: item.statement,
                            relevance: item.relevance,
                        })
                        .collect(),
                })?,
            )?,
            false,
        )),
        Err(error) => Ok((
            error_response(request_id, map_storage_error(&error, false))?,
            false,
        )),
    }
}

fn handle_record_usage(
    service: &mut SqliteCoreService,
    payload: Value,
    request_id: &str,
) -> Result<(CoreResponseEnvelope, bool), DaemonError> {
    let payload: RecordContextUsagePayload = match parse_payload(payload) {
        Ok(payload) => payload,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, false))?,
                false,
            ));
        }
    };
    let input = match payload.into_domain() {
        Ok(input) => input,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, false))?,
                false,
            ));
        }
    };
    match service.record_context_usage(&RecordContextUsageCommand {
        usage_id: request_id.to_owned(),
        memory_space_id: input.memory_space_id,
        item_ids: input.item_ids,
        used_at: OffsetDateTime::now_utc(),
        session_id: None,
        round_id: None,
    }) {
        Ok(()) => Ok((
            CoreResponseEnvelope::ok(
                request_id,
                serde_json::to_value(RecordContextUsageResultPayload { recorded: true })?,
            )?,
            false,
        )),
        Err(error) => Ok((
            error_response(request_id, map_storage_error(&error, false))?,
            false,
        )),
    }
}

fn handle_poll_projection_events(
    service: &SqliteCoreService,
    payload: Value,
    request_id: &str,
) -> Result<(CoreResponseEnvelope, bool), DaemonError> {
    let payload: PollProjectionEventsPayload = match parse_payload(payload) {
        Ok(payload) => payload,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, false))?,
                false,
            ));
        }
    };
    if payload.memory_space_id.trim().is_empty() || payload.consumer_id.trim().is_empty() {
        return Ok((
            error_response(
                request_id,
                (
                    CoreErrorCode::InvalidRequest,
                    "memory_space_id and consumer_id must not be empty".to_owned(),
                    false,
                ),
            )?,
            false,
        ));
    }
    if !(1..=1000).contains(&payload.limit) {
        return Ok((
            error_response(
                request_id,
                (
                    CoreErrorCode::InvalidRequest,
                    "limit must be between 1 and 1000".to_owned(),
                    false,
                ),
            )?,
            false,
        ));
    }
    let memory_space_id = MemorySpaceId::try_from(payload.memory_space_id)
        .map_err(|error| ProtocolError::Invalid(error.to_string()))?;
    let after_event_id = payload
        .after_event_id
        .map(|value| {
            ProjectionEventId::try_from(value)
                .map_err(|error| ProtocolError::Invalid(error.to_string()))
        })
        .transpose()?;
    let request = PollProjectionEventsRequest {
        memory_space_id,
        consumer_id: payload.consumer_id,
        after_event_id,
        limit: payload.limit,
    };
    match service.poll_projection_events(&request) {
        Ok(page) => {
            let has_more = page.has_more;
            let events = page
                .events
                .into_iter()
                .map(|event| {
                    Ok(ProjectionEventPayload {
                        event_id: event.projection_event_id.to_string(),
                        memory_space_id: event.memory_space_id.to_string(),
                        aggregate_id: event.aggregate_id,
                        event_type: event.event_type,
                        payload: serde_json::from_str(&event.payload_json)?,
                        occurred_at: event
                            .occurred_at
                            .format(&time::format_description::well_known::Rfc3339)
                            .map_err(|error| ProtocolError::Invalid(error.to_string()))?,
                    })
                })
                .collect::<Result<Vec<_>, DaemonError>>()?;
            Ok((
                CoreResponseEnvelope::ok(
                    request_id,
                    serde_json::to_value(PollProjectionEventsResultPayload { events, has_more })?,
                )?,
                false,
            ))
        }
        Err(error) => Ok((
            error_response(request_id, map_storage_error(&error, false))?,
            false,
        )),
    }
}

fn handle_ack_projection_events(
    service: &mut SqliteCoreService,
    payload: Value,
    request_id: &str,
) -> Result<(CoreResponseEnvelope, bool), DaemonError> {
    let payload: AckProjectionEventsPayload = match parse_payload(payload) {
        Ok(payload) => payload,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, false))?,
                false,
            ));
        }
    };
    if payload.consumer_id.trim().is_empty() || payload.event_ids.is_empty() {
        return Ok((
            error_response(
                request_id,
                (
                    CoreErrorCode::InvalidRequest,
                    "consumer_id and event_ids must not be empty".to_owned(),
                    false,
                ),
            )?,
            false,
        ));
    }
    let event_ids = payload
        .event_ids
        .into_iter()
        .map(|value| {
            ProjectionEventId::try_from(value)
                .map_err(|error| ProtocolError::Invalid(error.to_string()))
        })
        .collect::<Result<Vec<_>, _>>()?;
    match service.ack_projection_events(&AckProjectionEventsCommand {
        consumer_id: payload.consumer_id,
        event_ids,
    }) {
        Ok(acknowledged) => Ok((
            CoreResponseEnvelope::ok(
                request_id,
                serde_json::to_value(AckProjectionEventsResultPayload {
                    acknowledged: acknowledged
                        .into_iter()
                        .map(|event_id| event_id.to_string())
                        .collect(),
                })?,
            )?,
            false,
        )),
        Err(error) => Ok((
            error_response(request_id, map_storage_error(&error, false))?,
            false,
        )),
    }
}

fn handle_poll_model_tasks(
    service: &mut SqliteCoreService,
    payload: Value,
    request_id: &str,
) -> Result<(CoreResponseEnvelope, bool), DaemonError> {
    let payload: PollModelTasksPayload = match parse_payload(payload) {
        Ok(payload) => payload,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, false))?,
                false,
            ));
        }
    };
    if let Err(error) = payload.validate() {
        return Ok((
            error_response(request_id, map_protocol_error(&error, false))?,
            false,
        ));
    }
    let memory_space_id = MemorySpaceId::try_from(payload.memory_space_id)
        .map_err(|error| ProtocolError::Invalid(error.to_string()))?;
    match service.poll_model_tasks(&PollModelTasksRequest {
        memory_space_id,
        worker_id: payload.worker_id,
        limit: payload.limit,
        lease_seconds: payload.lease_seconds,
    }) {
        Ok(page) => {
            let mut tasks = Vec::with_capacity(page.tasks.len());
            for record in page.tasks {
                let mut task: ModelTaskPayload = match serde_json::from_str(&record.payload_json) {
                    Ok(task) => task,
                    Err(error) => {
                        return Ok((
                            error_response(
                                request_id,
                                (
                                    CoreErrorCode::IntegrityViolation,
                                    format!("stored model task payload is invalid: {error}"),
                                    false,
                                ),
                            )?,
                            false,
                        ));
                    }
                };
                if task.task_id != record.task_id.to_string()
                    || task.memory_space_id != record.memory_space_id.to_string()
                    || task.operation != record.task_type
                {
                    return Ok((
                        error_response(
                            request_id,
                            (
                                CoreErrorCode::IntegrityViolation,
                                format!("stored model task {} metadata mismatch", record.task_id),
                                false,
                            ),
                        )?,
                        false,
                    ));
                }
                task.lease_expires_at = record.lease_expires_at.map(|value| {
                    value
                        .format(&time::format_description::well_known::Rfc3339)
                        .unwrap_or_else(|_| value.to_string())
                });
                if let Err(error) = task.validate() {
                    return Ok((
                        error_response(
                            request_id,
                            (CoreErrorCode::IntegrityViolation, error.to_string(), false),
                        )?,
                        false,
                    ));
                }
                tasks.push(task);
            }
            Ok((
                CoreResponseEnvelope::ok(
                    request_id,
                    serde_json::to_value(PollModelTasksResultPayload {
                        tasks,
                        has_more: page.has_more,
                    })?,
                )?,
                false,
            ))
        }
        Err(error) => Ok((
            error_response(request_id, map_storage_error(&error, false))?,
            false,
        )),
    }
}

fn handle_submit_model_result(
    service: &mut SqliteCoreService,
    payload: Value,
    request_id: &str,
) -> Result<(CoreResponseEnvelope, bool), DaemonError> {
    let payload: SubmitModelResultPayload = match parse_payload(payload) {
        Ok(payload) => payload,
        Err(error) => {
            return Ok((
                error_response(request_id, map_protocol_error(&error, false))?,
                false,
            ));
        }
    };
    if let Err(error) = payload.validate() {
        return Ok((
            error_response(request_id, map_protocol_error(&error, false))?,
            false,
        ));
    }
    let task_id = ModelTaskId::try_from(payload.task_id)
        .map_err(|error| ProtocolError::Invalid(error.to_string()))?;
    let memory_space_id = MemorySpaceId::try_from(payload.memory_space_id)
        .map_err(|error| ProtocolError::Invalid(error.to_string()))?;
    let result_json = serde_json::to_string(&payload.result)?;
    match service.submit_model_result(&SubmitModelResultCommand {
        task_id,
        memory_space_id,
        worker_id: payload.worker_id,
        result_json,
    }) {
        Ok(result) => Ok((
            CoreResponseEnvelope::ok(
                request_id,
                serde_json::to_value(SubmitModelResultResultPayload {
                    accepted: result.accepted,
                    duplicate: result.duplicate,
                    status: result.status,
                })?,
            )?,
            false,
        )),
        Err(error) => Ok((
            error_response(request_id, map_storage_error(&error, false))?,
            false,
        )),
    }
}

fn parse_payload<T: DeserializeOwned>(payload: Value) -> Result<T, ProtocolError> {
    serde_json::from_value(payload).map_err(ProtocolError::Json)
}

fn error_response(
    request_id: &str,
    (code, message, retryable): (CoreErrorCode, String, bool),
) -> Result<CoreResponseEnvelope, ProtocolError> {
    CoreResponseEnvelope::error(
        request_id,
        CoreError::new(code, message, Uuid::new_v4().to_string(), retryable)?,
    )
}

fn map_protocol_error(error: &ProtocolError, hypothesis: bool) -> (CoreErrorCode, String, bool) {
    let code = match error {
        ProtocolError::UnsupportedVersion(_) => CoreErrorCode::ProtocolVersionUnsupported,
        ProtocolError::Domain(_) | ProtocolError::Identifier(_) if hypothesis => {
            CoreErrorCode::InvalidHypothesis
        }
        _ => CoreErrorCode::InvalidRequest,
    };
    (code, error.to_string(), false)
}

fn map_storage_error(error: &StorageError, hypothesis: bool) -> (CoreErrorCode, String, bool) {
    let code = match error {
        StorageError::IdempotencyConflict { .. } => CoreErrorCode::IdempotencyConflict,
        StorageError::NotFound(_) => CoreErrorCode::NotFound,
        StorageError::VersionConflict { .. } => CoreErrorCode::VersionConflict,
        StorageError::StaleModelTask(_) => CoreErrorCode::StaleModelTask,
        StorageError::Domain(_) if hypothesis => CoreErrorCode::InvalidHypothesis,
        StorageError::InvalidRecord(_) if hypothesis => CoreErrorCode::InvalidHypothesis,
        StorageError::InvalidRecord(_) => CoreErrorCode::InvalidRequest,
        StorageError::Integrity(_) => CoreErrorCode::IntegrityViolation,
        StorageError::Sqlite(_) | StorageError::Io(_) | StorageError::Transaction(_) => {
            CoreErrorCode::StorageUnavailable
        }
        _ => CoreErrorCode::InternalError,
    };
    let retryable = matches!(code, CoreErrorCode::StorageUnavailable);
    (code, error.to_string(), retryable)
}
