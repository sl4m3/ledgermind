CREATE TABLE projection_event_acknowledgements (
    consumer_id TEXT NOT NULL,
    projection_event_id TEXT NOT NULL
        REFERENCES projection_events(projection_event_id) ON DELETE CASCADE,
    acknowledged_at TEXT NOT NULL,
    PRIMARY KEY (consumer_id, projection_event_id),
    CHECK (length(consumer_id) >= 1)
);

CREATE INDEX ix_projection_event_ack_consumer
ON projection_event_acknowledgements (consumer_id, projection_event_id);
