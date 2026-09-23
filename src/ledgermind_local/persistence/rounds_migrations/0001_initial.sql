CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE memory_spaces (
    memory_space_id TEXT PRIMARY KEY,
    display_name TEXT,
    source_client TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (length(memory_space_id) BETWEEN 1 AND 200)
);

CREATE TABLE raw_rounds (
    raw_round_id TEXT PRIMARY KEY,
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    source_system TEXT NOT NULL,
    source_instance_id TEXT NOT NULL,
    source_profile_id TEXT NOT NULL,
    source_session_id TEXT NOT NULL,
    source_round_id TEXT NOT NULL,
    source_round_key TEXT NOT NULL,
    capture_schema_version INTEGER NOT NULL,
    adapter_version TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    payload_digest TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    retention_expires_at TEXT,
    CHECK (capture_schema_version >= 1),
    CHECK (payload_digest GLOB 'sha256:*'),
    UNIQUE (memory_space_id, source_round_key, capture_schema_version)
);

CREATE INDEX ix_raw_rounds_memory_received
ON raw_rounds (memory_space_id, received_at DESC);

CREATE TABLE raw_round_payloads (
    raw_round_id TEXT PRIMARY KEY
        REFERENCES raw_rounds(raw_round_id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL,
    payload_bytes INTEGER NOT NULL,
    retention_expires_at TEXT,
    deleted_at TEXT,
    CHECK (payload_bytes >= 0)
);

CREATE INDEX ix_raw_round_payloads_retention
ON raw_round_payloads (retention_expires_at, raw_round_id)
WHERE deleted_at IS NULL;

CREATE TABLE round_processing_jobs (
    job_id TEXT PRIMARY KEY,
    raw_round_id TEXT NOT NULL
        REFERENCES raw_rounds(raw_round_id) ON DELETE CASCADE,
    pipeline_version INTEGER NOT NULL,
    normalizer_version INTEGER NOT NULL,
    prompt_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    claimed_at TEXT,
    claimed_by TEXT,
    completed_at TEXT,
    last_error TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    CHECK (pipeline_version >= 1),
    CHECK (normalizer_version >= 1),
    CHECK (prompt_version >= 1),
    CHECK (status IN ('received', 'processing', 'retry_wait', 'completed', 'no_knowledge', 'failed')),
    UNIQUE (raw_round_id, pipeline_version, normalizer_version, prompt_version)
);

CREATE INDEX ix_round_processing_jobs_claimable
ON round_processing_jobs (status, available_at, lease_expires_at, job_id);

CREATE TABLE hypothesis_attempts (
    attempt_id TEXT PRIMARY KEY,
    raw_round_id TEXT NOT NULL
        REFERENCES raw_rounds(raw_round_id) ON DELETE CASCADE,
    job_id TEXT NOT NULL
        REFERENCES round_processing_jobs(job_id) ON DELETE CASCADE,
    pipeline_version INTEGER NOT NULL,
    normalizer_version INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    response_digest TEXT,
    error_code TEXT,
    error_detail TEXT
);

CREATE TABLE hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    raw_round_id TEXT NOT NULL
        REFERENCES raw_rounds(raw_round_id) ON DELETE CASCADE,
    attempt_id TEXT NOT NULL
        REFERENCES hypothesis_attempts(attempt_id) ON DELETE RESTRICT,
    hypothesis_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    target TEXT NOT NULL,
    statement TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    artifacts_json TEXT NOT NULL DEFAULT '[]',
    content_digest TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'generated',
    core_command_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (attempt_id, hypothesis_index),
    CHECK (hypothesis_index >= 0),
    CHECK (content_digest GLOB 'sha256:*'),
    CHECK (status IN ('generated', 'queued_for_core', 'accepted_by_core', 'rejected_by_core'))
);

CREATE INDEX ix_hypotheses_raw_round
ON hypotheses (raw_round_id, created_at);

CREATE INDEX ix_hypotheses_core_status
ON hypotheses (status, created_at);

CREATE TABLE normalized_rounds (
    normalized_round_id TEXT PRIMARY KEY,
    raw_round_id TEXT NOT NULL
        REFERENCES raw_rounds(raw_round_id) ON DELETE CASCADE,
    normalizer_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (raw_round_id, normalizer_version),
    CHECK (normalizer_version >= 1),
    CHECK (payload_digest GLOB 'sha256:*')
);

CREATE INDEX ix_normalized_rounds_raw_round
ON normalized_rounds (raw_round_id, normalizer_version);

CREATE TABLE inference_profiles (
    profile_id TEXT PRIMARY KEY,
    provider_kind TEXT NOT NULL DEFAULT 'openai_compatible',
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    secret_ref TEXT NOT NULL,
    timeout_seconds REAL NOT NULL DEFAULT 60.0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    max_input_tokens INTEGER NOT NULL DEFAULT 12000,
    max_output_tokens INTEGER NOT NULL DEFAULT 2000,
    hypothesis_prompt_version INTEGER NOT NULL DEFAULT 1,
    hypothesis_schema_version INTEGER NOT NULL DEFAULT 1,
    merge_prompt_version INTEGER NOT NULL DEFAULT 1,
    merge_schema_version INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (provider_kind = 'openai_compatible'),
    CHECK (timeout_seconds > 0 AND timeout_seconds <= 600),
    CHECK (max_retries BETWEEN 0 AND 5),
    CHECK (max_input_tokens > 0),
    CHECK (max_output_tokens > 0),
    CHECK (hypothesis_prompt_version >= 1),
    CHECK (hypothesis_schema_version >= 1),
    CHECK (merge_prompt_version >= 1),
    CHECK (merge_schema_version >= 1),
    CHECK (enabled IN (0, 1))
);

CREATE INDEX ix_inference_profiles_enabled
ON inference_profiles (enabled, profile_id);

CREATE TABLE memory_space_inference_profiles (
    memory_space_id TEXT PRIMARY KEY
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    hypothesis_profile_id TEXT REFERENCES inference_profiles(profile_id) ON DELETE SET NULL,
    merge_profile_id TEXT REFERENCES inference_profiles(profile_id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL,
    CHECK (hypothesis_profile_id IS NOT NULL OR merge_profile_id IS NOT NULL)
);

CREATE TABLE egress_audit (
    audit_id TEXT PRIMARY KEY,
    memory_space_id TEXT,
    profile_id TEXT,
    operation TEXT NOT NULL,
    provider_kind TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    request_bytes INTEGER NOT NULL DEFAULT 0,
    response_bytes INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    created_at TEXT NOT NULL,
    CHECK (request_bytes >= 0),
    CHECK (response_bytes >= 0),
    CHECK (attempts >= 0)
);

CREATE INDEX ix_egress_audit_created
ON egress_audit (created_at DESC);

CREATE TABLE core_commands (
    command_id TEXT PRIMARY KEY,
    command_type TEXT NOT NULL,
    memory_space_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    lease_expires_at TEXT,
    claimed_by TEXT,
    completed_at TEXT,
    result_json TEXT,
    last_error_code TEXT,
    last_error_detail TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(memory_space_id, idempotency_key),
    CHECK (status IN ('pending', 'delivering', 'retry_wait', 'completed', 'rejected', 'failed')),
    CHECK (attempts >= 0),
    CHECK (payload_digest GLOB 'sha256:*')
);

CREATE INDEX ix_core_commands_claimable
ON core_commands (status, available_at, lease_expires_at, command_id);

CREATE INDEX ix_core_commands_memory_idempotency
ON core_commands (memory_space_id, idempotency_key);

CREATE TABLE projection_state (
    projection_name TEXT PRIMARY KEY,
    projection_version INTEGER NOT NULL,
    last_event_id TEXT,
    updated_at TEXT NOT NULL,
    CHECK (projection_version >= 1)
);

CREATE TABLE core_event_inbox (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    processed_at TEXT,
    last_error TEXT
);

CREATE INDEX ix_core_event_inbox_ready
ON core_event_inbox (received_at, event_id)
WHERE processed_at IS NULL;

CREATE TABLE context_items (
    knowledge_id TEXT PRIMARY KEY,
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    target TEXT NOT NULL,
    statement TEXT NOT NULL,
    relevance REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    CHECK (relevance >= 0.0 AND relevance <= 1.0)
);

CREATE INDEX ix_context_items_space_updated
ON context_items (memory_space_id, updated_at DESC)
WHERE deleted_at IS NULL;

CREATE VIRTUAL TABLE context_fts USING fts5(
    knowledge_id UNINDEXED,
    memory_space_id UNINDEXED,
    title,
    target,
    statement,
    tokenize='unicode61'
);
