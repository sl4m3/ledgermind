CREATE TABLE memory_space_model_profiles_v2 (
    memory_space_id TEXT NOT NULL
        REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    profile_slot TEXT NOT NULL CHECK (
        profile_slot IN ('operational', 'object_resolution', 'background', 'embedding')
    ),
    profile_id TEXT NOT NULL
        REFERENCES inference_profiles(profile_id) ON DELETE CASCADE,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (memory_space_id, profile_slot)
);

INSERT INTO memory_space_model_profiles_v2 (
    memory_space_id, profile_slot, profile_id, updated_at
)
SELECT memory_space_id, profile_slot, profile_id, updated_at
FROM memory_space_model_profiles;

DROP TABLE memory_space_model_profiles;

ALTER TABLE memory_space_model_profiles_v2
    RENAME TO memory_space_model_profiles;
