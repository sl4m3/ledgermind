CREATE TABLE memory_space_model_profiles (
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    profile_slot TEXT NOT NULL CHECK (profile_slot IN ('operational', 'background', 'embedding')),
    profile_id TEXT NOT NULL
        REFERENCES inference_profiles(profile_id) ON DELETE CASCADE,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (memory_space_id, profile_slot)
);

CREATE TABLE raw_round_core_deliveries (
    raw_round_id TEXT PRIMARY KEY,
    memory_space_id TEXT NOT NULL,
    command_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL,
    transport_status TEXT NOT NULL CHECK (transport_status IN ('queued', 'accepted', 'rejected', 'retry_wait')),
    core_raw_round_id TEXT,
    core_job_id TEXT,
    last_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (raw_round_id) REFERENCES raw_rounds(raw_round_id) ON DELETE CASCADE
);

INSERT INTO memory_space_model_profiles (
    memory_space_id, profile_slot, profile_id, updated_at
)
SELECT memory_space_id, 'operational', hypothesis_profile_id, updated_at
FROM memory_space_inference_profiles
WHERE hypothesis_profile_id IS NOT NULL;

INSERT INTO memory_space_model_profiles (
    memory_space_id, profile_slot, profile_id, updated_at
)
SELECT memory_space_id, 'background', merge_profile_id, updated_at
FROM memory_space_inference_profiles
WHERE merge_profile_id IS NOT NULL;

CREATE INDEX raw_round_core_deliveries_status_idx
    ON raw_round_core_deliveries (memory_space_id, transport_status);
