ALTER TABLE projection_state RENAME TO projection_state_legacy;

CREATE TABLE projection_state (
    projection_name TEXT PRIMARY KEY,
    projection_version INTEGER NOT NULL,
    rebuilt_at TEXT,
    item_count INTEGER NOT NULL DEFAULT 0,
    checksum TEXT,
    last_event_id TEXT,
    updated_at TEXT NOT NULL DEFAULT '',
    CHECK (item_count >= 0),
    CHECK (projection_version >= 1)
);

INSERT INTO projection_state (
    projection_name,
    projection_version,
    rebuilt_at,
    item_count,
    checksum,
    last_event_id,
    updated_at
)
SELECT
    projection_name,
    projection_version,
    NULL,
    0,
    NULL,
    last_event_id,
    COALESCE(updated_at, '')
FROM projection_state_legacy;

DROP TABLE projection_state_legacy;
