-- Only Local profile metadata changes. Core knowledge.db is not migrated.
ALTER TABLE inference_profiles ADD COLUMN decision_backend TEXT
    CHECK (decision_backend IS NULL OR decision_backend IN ('jev','kev','generative'));

CREATE TABLE memory_space_model_profiles_v3 (
    memory_space_id TEXT NOT NULL REFERENCES memory_spaces(memory_space_id) ON DELETE CASCADE,
    profile_slot TEXT NOT NULL CHECK (profile_slot IN
        ('operational','object_resolution','background','embedding','resolution_decision')),
    profile_id TEXT NOT NULL REFERENCES inference_profiles(profile_id) ON DELETE CASCADE,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (memory_space_id, profile_slot)
);
INSERT INTO memory_space_model_profiles_v3 SELECT * FROM memory_space_model_profiles;
DROP TABLE memory_space_model_profiles;
ALTER TABLE memory_space_model_profiles_v3 RENAME TO memory_space_model_profiles;
