CREATE TABLE IF NOT EXISTS schema_migrations (
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

CREATE TABLE hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    content_digest TEXT NOT NULL,
    title TEXT NOT NULL,
    target TEXT NOT NULL,
    statement TEXT NOT NULL,
    rationale TEXT NOT NULL,
    result TEXT NOT NULL,
    artifacts_json TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_instance_id TEXT NOT NULL,
    source_profile_id TEXT NOT NULL,
    source_session_id TEXT NOT NULL,
    source_round_id TEXT NOT NULL,
    source_event_ids_json TEXT NOT NULL,
    raw_round_digest TEXT NOT NULL,
    normalized_round_digest TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    completed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (length(title) BETWEEN 1 AND 240),
    CHECK (length(target) BETWEEN 1 AND 240),
    CHECK (length(statement) >= 1),
    CHECK (prompt_version >= 1),
    CHECK (schema_version >= 1),
    CHECK (content_digest GLOB 'sha256:*'),
    CHECK (raw_round_digest GLOB 'sha256:*'),
    CHECK (normalized_round_digest GLOB 'sha256:*')
);

CREATE INDEX ix_hypotheses_memory_created
    ON hypotheses (memory_space_id, created_at);

CREATE TABLE knowledge_items (
    knowledge_id TEXT PRIMARY KEY,
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    target TEXT NOT NULL,
    statement TEXT NOT NULL,
    rationale TEXT NOT NULL,
    phase TEXT NOT NULL,
    version INTEGER NOT NULL,
    current_revision_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    superseded_by_id TEXT REFERENCES knowledge_items(knowledge_id),
    deleted_at TEXT,
    CHECK (length(title) BETWEEN 1 AND 240),
    CHECK (length(target) BETWEEN 1 AND 240),
    CHECK (length(statement) >= 1),
    CHECK (phase IN ('pattern', 'emergent', 'canonical')),
    CHECK (version >= 1),
    CHECK (superseded_by_id IS NULL OR superseded_by_id <> knowledge_id)
);

CREATE INDEX ix_knowledge_current_space
    ON knowledge_items (memory_space_id, target, phase)
    WHERE superseded_by_id IS NULL AND deleted_at IS NULL;

CREATE INDEX ix_knowledge_updated
    ON knowledge_items (memory_space_id, updated_at DESC);

CREATE TABLE knowledge_revisions (
    revision_id TEXT PRIMARY KEY,
    knowledge_id TEXT NOT NULL
        REFERENCES knowledge_items(knowledge_id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    cause_hypothesis_id TEXT
        REFERENCES hypotheses(hypothesis_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    UNIQUE (knowledge_id, version),
    CHECK (version >= 1),
    CHECK (length(event_type) >= 1),
    CHECK (json_valid(snapshot_json)),
    CHECK (json_type(snapshot_json) = 'object')
);

CREATE INDEX ix_revisions_knowledge_version
    ON knowledge_revisions (knowledge_id, version);

CREATE TABLE evidence_links (
    knowledge_id TEXT NOT NULL
        REFERENCES knowledge_items(knowledge_id) ON DELETE CASCADE,
    hypothesis_id TEXT NOT NULL
        REFERENCES hypotheses(hypothesis_id) ON DELETE RESTRICT,
    relation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (knowledge_id, hypothesis_id, relation),
    CHECK (relation IN ('origin', 'supports', 'contradicts', 'refines'))
);

CREATE INDEX ix_evidence_hypothesis
    ON evidence_links (hypothesis_id, knowledge_id);

CREATE TABLE supersession_links (
    predecessor_knowledge_id TEXT NOT NULL
        REFERENCES knowledge_items(knowledge_id) ON DELETE CASCADE,
    successor_knowledge_id TEXT NOT NULL
        REFERENCES knowledge_items(knowledge_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (predecessor_knowledge_id, successor_knowledge_id),
    CHECK (predecessor_knowledge_id <> successor_knowledge_id)
);

CREATE TABLE idempotency_results (
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    PRIMARY KEY (memory_space_id, idempotency_key),
    CHECK (idempotency_key LIKE 'sha256:%'),
    CHECK (request_hash GLOB 'sha256:*'),
    CHECK (json_valid(response_json))
);

CREATE TABLE model_tasks (
    task_id TEXT PRIMARY KEY,
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (length(task_type) >= 1),
    CHECK (length(status) >= 1),
    CHECK (request_digest GLOB 'sha256:*'),
    CHECK (json_valid(payload_json)),
    CHECK (result_json IS NULL OR json_valid(result_json))
);

CREATE INDEX ix_model_tasks_memory_status
    ON model_tasks (memory_space_id, status, updated_at);

CREATE TABLE context_usage (
    usage_id TEXT PRIMARY KEY,
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    knowledge_id TEXT REFERENCES knowledge_items(knowledge_id) ON DELETE SET NULL,
    surface TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    used_at TEXT NOT NULL,
    CHECK (length(surface) >= 1),
    CHECK (json_valid(metadata_json))
);

CREATE INDEX ix_context_usage_memory_time
    ON context_usage (memory_space_id, used_at);

CREATE TABLE projection_events (
    projection_event_id TEXT PRIMARY KEY,
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    CHECK (length(aggregate_id) >= 1),
    CHECK (length(event_type) >= 1),
    CHECK (json_valid(payload_json))
);

CREATE UNIQUE INDEX ux_projection_event_aggregate_type
    ON projection_events (aggregate_id, event_type, occurred_at);

CREATE INDEX ix_projection_events_memory_time
    ON projection_events (memory_space_id, occurred_at);
