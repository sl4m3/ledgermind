CREATE TABLE core_projection_events (
    event_id TEXT PRIMARY KEY,
    memory_space_id TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    CHECK (length(memory_space_id) >= 1),
    CHECK (length(aggregate_id) >= 1),
    CHECK (length(event_type) >= 1),
    CHECK (json_valid(payload_json))
);

CREATE INDEX ix_core_projection_events_order
ON core_projection_events (memory_space_id, occurred_at, event_id);

CREATE TABLE core_projection_deliveries (
    projection_name TEXT NOT NULL,
    event_id TEXT NOT NULL
        REFERENCES core_projection_events(event_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    processed_at TEXT,
    last_error TEXT,
    PRIMARY KEY (projection_name, event_id),
    CHECK (status IN ('pending', 'failed', 'processed')),
    CHECK (attempts >= 0)
);

CREATE INDEX ix_core_projection_deliveries_ready
ON core_projection_deliveries (projection_name, available_at, event_id)
WHERE status IN ('pending', 'failed');
