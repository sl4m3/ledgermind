CREATE TABLE contract_migration_markers (
    marker TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

UPDATE core_commands
SET command_type = 'ingest_raw_round'
WHERE command_type = 'ingest_raw_round_v2';

INSERT INTO contract_migration_markers (marker, applied_at)
VALUES ('contract_naming', CURRENT_TIMESTAMP);
