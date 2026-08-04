use std::process::{Command, Stdio};

use ledgermind_application::ModelTaskRecord;
use ledgermind_daemon::{read_frame, write_frame};
use ledgermind_domain::{MemorySpaceId, ModelTaskId, Sha256Digest};
use ledgermind_protocol::{CoreErrorCode, CoreRequestEnvelope, CoreResponseEnvelope, Operation};
use ledgermind_storage_sqlite::SqliteCoreService;
use serde_json::json;
use tempfile::tempdir;
use time::OffsetDateTime;

fn digest(pair: &str) -> String {
    format!("sha256:{}", pair.repeat(32))
}

fn exchange(
    input: &mut impl std::io::Write,
    output: &mut impl std::io::Read,
    request: CoreRequestEnvelope,
) -> CoreResponseEnvelope {
    write_frame(input, request.to_json().as_bytes()).expect("request is framed");
    let response = read_frame(output)
        .expect("response frame is readable")
        .expect("daemon returns a response");
    CoreResponseEnvelope::from_json(std::str::from_utf8(&response).unwrap())
        .expect("response follows protocol v1")
}

#[test]
fn daemon_process_handles_vertical_slice_over_stdio() {
    let temporary = tempdir().expect("temporary directory");
    let database = temporary.path().join("knowledge.db");
    let mut child = Command::new(env!("CARGO_BIN_EXE_ledgermind-core"))
        .arg("--database")
        .arg(&database)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("daemon starts");
    let mut input = child.stdin.take().expect("daemon stdin");
    let mut output = child.stdout.take().expect("daemon stdout");

    let handshake = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "request-handshake",
            Operation::Handshake,
            json!({
                "client_name": "integration-test",
                "client_version": "0.1.0",
                "supported_operations": [
                    "handshake",
                    "health",
                    "accept_hypothesis",
                    "retrieve_context",
                    "record_context_usage",
                    "poll_projection_events",
                    "ack_projection_events",
                    "poll_model_tasks",
                    "submit_model_result",
                    "shutdown"
                ]
            }),
        )
        .unwrap(),
    );
    assert_eq!(handshake.status, ledgermind_protocol::ResponseStatus::Ok);
    assert_eq!(handshake.result.unwrap()["protocol_version"], 1);

    let health = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new("request-health", Operation::Health, json!({})).unwrap(),
    );
    let health_result = health.result.unwrap();
    assert_eq!(health_result["healthy"], true);
    assert_eq!(health_result["protocol_version"], 1);
    assert_eq!(health_result["schema_version"], 4);
    assert!(health_result["environment_keys"].is_array());

    let memory_space_id = "memory-space-daemon";
    let accept = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "command-daemon-1",
            Operation::AcceptHypothesis,
            json!({
                "protocol_version": 1,
                "command_id": "command-daemon-1",
                "idempotency_key": digest("ab"),
                "memory_space_id": memory_space_id,
                "hypothesis": {
                    "hypothesis_id": "hypothesis-daemon-1",
                    "content_digest": digest("cd"),
                    "title": "Daemon context",
                    "target": "Rust Core",
                    "statement": "The daemon serves current context",
                    "rationale": "stdio integration",
                    "result": "accepted",
                    "artifacts": [],
                    "evidence": {
                        "source_system": "local",
                        "source_instance_id": "instance",
                        "source_profile_id": "profile",
                        "source_session_id": "session",
                        "source_round_id": "round",
                        "raw_round_digest": digest("ef"),
                        "normalized_round_digest": digest("01"),
                        "source_event_ids": ["source-event-daemon-1"]
                    },
                    "extraction": {
                        "provider": "provider",
                        "model": "model",
                        "prompt_version": 1,
                        "schema_version": 1,
                        "completed_at": "2023-11-14T22:13:20Z"
                    }
                }
            }),
        )
        .unwrap(),
    );
    let accept_result = accept.result.unwrap();
    assert_eq!(accept_result["accepted"], true);
    let knowledge_id = accept_result["core_reference_id"]
        .as_str()
        .expect("accept returns knowledge reference")
        .to_owned();

    let poll = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "request-poll-1",
            Operation::PollProjectionEvents,
            json!({
                "memory_space_id": memory_space_id,
                "consumer_id": "local-projections",
                "after_event_id": null,
                "limit": 10
            }),
        )
        .unwrap(),
    );
    let poll_result = poll.result.unwrap();
    let events = poll_result["events"].as_array().unwrap();
    assert_eq!(events.len(), 1);
    assert_eq!(events[0]["event_type"], "knowledge_projection_upsert");
    assert_eq!(events[0]["payload"]["knowledge_id"], knowledge_id);
    assert!(events[0]["payload"].get("phase").is_none());
    let event_id = events[0]["event_id"].as_str().unwrap().to_owned();

    let replay = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "request-poll-replay",
            Operation::PollProjectionEvents,
            json!({
                "memory_space_id": memory_space_id,
                "consumer_id": "local-projections",
                "after_event_id": null,
                "limit": 10
            }),
        )
        .unwrap(),
    );
    assert_eq!(
        replay.result.unwrap()["events"].as_array().unwrap().len(),
        1
    );

    let ack = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "request-ack",
            Operation::AckProjectionEvents,
            json!({
                "consumer_id": "local-projections",
                "event_ids": [event_id]
            }),
        )
        .unwrap(),
    );
    assert_eq!(
        ack.result.unwrap()["acknowledged"]
            .as_array()
            .unwrap()
            .len(),
        1
    );

    let after_ack = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "request-poll-after-ack",
            Operation::PollProjectionEvents,
            json!({
                "memory_space_id": memory_space_id,
                "consumer_id": "local-projections",
                "after_event_id": null,
                "limit": 10
            }),
        )
        .unwrap(),
    );
    assert!(
        after_ack.result.unwrap()["events"]
            .as_array()
            .unwrap()
            .is_empty()
    );

    let context = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "request-context",
            Operation::RetrieveContext,
            json!({
                "memory_space_id": memory_space_id,
                "query": "daemon context",
                "limit": 5
            }),
        )
        .unwrap(),
    );
    let context_result = context.result.unwrap();
    assert_eq!(context_result["api_version"], "1");
    let items = context_result["items"].as_array().unwrap();
    assert_eq!(items.len(), 1);
    assert_eq!(items[0]["knowledge_id"], knowledge_id);

    let usage = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "request-usage",
            Operation::RecordContextUsage,
            json!({
                "memory_space_id": memory_space_id,
                "item_ids": [knowledge_id]
            }),
        )
        .unwrap(),
    );
    assert_eq!(usage.result.unwrap()["recorded"], true);

    let shutdown = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new("request-shutdown", Operation::Shutdown, json!({})).unwrap(),
    );
    assert_eq!(shutdown.result.unwrap()["stopped"], true);
    drop(input);
    let status = child.wait().expect("daemon exits after shutdown");
    assert!(status.success());
}

#[test]
fn daemon_process_polls_leases_and_idempotently_accepts_model_result() {
    let temporary = tempdir().expect("temporary directory");
    let database = temporary.path().join("knowledge.db");
    let memory_space_id = MemorySpaceId::try_from("memory-space-model-task").unwrap();
    let task_id = ModelTaskId::try_from("model-task-daemon-1").unwrap();
    let now = OffsetDateTime::now_utc();
    let mut seed = SqliteCoreService::open(&database).expect("core database opens");
    seed.enqueue_model_task(&ModelTaskRecord {
        task_id: task_id.clone(),
        memory_space_id: memory_space_id.clone(),
        task_type: "merge_knowledge".to_owned(),
        status: "queued".to_owned(),
        request_digest: Sha256Digest::from_bytes(b"model-task-request"),
        payload_json: serde_json::to_string(&json!({
            "task_id": task_id,
            "operation": "merge_knowledge",
            "memory_space_id": memory_space_id,
            "expected_versions": {"knowledge-a": 1, "knowledge-b": 2},
            "expires_at": (now + time::Duration::hours(1))
                .format(&time::format_description::well_known::Rfc3339)
                .unwrap(),
            "model_input": {
                "items": [
                    {"reference": "knowledge-a", "required_constraints": ["keep source"]},
                    {"reference": "knowledge-b", "required_constraints": ["keep source"]}
                ]
            }
        }))
        .unwrap(),
        result_json: None,
        created_at: now,
        updated_at: now,
        expires_at: Some(now + time::Duration::hours(1)),
        lease_owner: None,
        lease_expires_at: None,
        attempts: 0,
    })
    .expect("model task is seeded");
    for (knowledge_id, title, version) in [
        ("knowledge-a", "Knowledge A", 1_i64),
        ("knowledge-b", "Knowledge B", 2_i64),
    ] {
        seed.database()
            .connection()
            .execute(
                "INSERT INTO knowledge_items(
                    knowledge_id, memory_space_id, title, target, statement, rationale,
                    phase, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    knowledge_id,
                    memory_space_id.as_str(),
                    title,
                    "ops",
                    format!("Statement for {title}"),
                    "Rationale",
                    "pattern",
                    version,
                    now.format(&time::format_description::well_known::Rfc3339)
                        .unwrap(),
                    now.format(&time::format_description::well_known::Rfc3339)
                        .unwrap(),
                ),
            )
            .expect("knowledge item is seeded");
    }
    drop(seed);

    let mut child = Command::new(env!("CARGO_BIN_EXE_ledgermind-core"))
        .arg("--database")
        .arg(&database)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("daemon starts");
    let mut input = child.stdin.take().expect("daemon stdin");
    let mut output = child.stdout.take().expect("daemon stdout");

    let poll = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "model-task-poll-1",
            Operation::PollModelTasks,
            json!({
                "memory_space_id": memory_space_id,
                "worker_id": "local-model-tasks",
                "limit": 10,
                "lease_seconds": 60
            }),
        )
        .unwrap(),
    );
    let poll_result = poll.result.unwrap();
    assert_eq!(poll_result["tasks"].as_array().unwrap().len(), 1);
    assert_eq!(poll_result["tasks"][0]["task_id"], task_id.to_string());
    assert!(poll_result["tasks"][0]["lease_expires_at"].is_string());

    let replay_poll = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "model-task-poll-2",
            Operation::PollModelTasks,
            json!({
                "memory_space_id": memory_space_id,
                "worker_id": "another-worker",
                "limit": 10,
                "lease_seconds": 60
            }),
        )
        .unwrap(),
    );
    assert!(
        replay_poll.result.unwrap()["tasks"]
            .as_array()
            .unwrap()
            .is_empty()
    );

    let stale = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "model-task-stale-submit",
            Operation::SubmitModelResult,
            json!({
                "task_id": task_id,
                "memory_space_id": memory_space_id,
                "worker_id": "another-worker",
                "result": {"title": "Merged"}
            }),
        )
        .unwrap(),
    );
    assert_eq!(stale.error.unwrap().code, CoreErrorCode::StaleModelTask);

    let invalid = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "model-task-invalid-submit",
            Operation::SubmitModelResult,
            json!({
                "task_id": task_id,
                "memory_space_id": memory_space_id,
                "worker_id": "local-model-tasks",
                "result": {
                    "title": "Merged",
                    "target": "ops",
                    "statement": "Merged statement",
                    "rationale": "Merged rationale",
                    "preserved_references": ["knowledge-a", "knowledge-b"],
                    "preserved_constraints": ["wrong constraint"],
                    "unexpected": true
                }
            }),
        )
        .unwrap(),
    );
    assert_eq!(invalid.error.unwrap().code, CoreErrorCode::InvalidRequest);

    let result = json!({
        "title": "Merged",
        "target": "ops",
        "statement": "Merged statement",
        "rationale": "Merged rationale",
        "preserved_references": ["knowledge-a", "knowledge-b"],
        "preserved_constraints": ["keep source"]
    });
    let submit = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "model-task-submit-1",
            Operation::SubmitModelResult,
            json!({
                "task_id": task_id,
                "memory_space_id": memory_space_id,
                "worker_id": "local-model-tasks",
                "result": result
            }),
        )
        .unwrap(),
    );
    let submit_result = submit.result.unwrap();
    assert_eq!(submit_result["accepted"], true);
    assert_eq!(submit_result["duplicate"], false);

    let replay = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new(
            "model-task-submit-replay",
            Operation::SubmitModelResult,
            json!({
                "task_id": task_id,
                "memory_space_id": memory_space_id,
                "worker_id": "local-model-tasks",
                "result": result
            }),
        )
        .unwrap(),
    );
    assert_eq!(replay.result.unwrap()["duplicate"], true);

    let shutdown = exchange(
        &mut input,
        &mut output,
        CoreRequestEnvelope::new("model-task-shutdown", Operation::Shutdown, json!({})).unwrap(),
    );
    assert_eq!(shutdown.result.unwrap()["stopped"], true);
    drop(input);
    assert!(child.wait().expect("daemon exits").success());
}
