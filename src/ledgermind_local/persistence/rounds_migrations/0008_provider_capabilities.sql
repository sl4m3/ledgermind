ALTER TABLE inference_profiles
    ADD COLUMN structured_output_preference TEXT NOT NULL DEFAULT 'auto';

ALTER TABLE inference_profiles
    ADD COLUMN token_parameter TEXT NOT NULL DEFAULT 'max_tokens';

ALTER TABLE inference_profiles
    ADD COLUMN supports_system_role INTEGER NOT NULL DEFAULT 1;

ALTER TABLE inference_profiles
    ADD COLUMN supports_seed INTEGER NOT NULL DEFAULT 0;

CREATE TABLE inference_provider_capabilities (
    profile_id TEXT PRIMARY KEY
        REFERENCES inference_profiles(profile_id) ON DELETE CASCADE,
    structured_output_mode TEXT NOT NULL DEFAULT 'auto',
    json_schema_supported INTEGER NOT NULL DEFAULT 0,
    tool_call_supported INTEGER NOT NULL DEFAULT 0,
    json_object_supported INTEGER NOT NULL DEFAULT 0,
    prompt_only_supported INTEGER NOT NULL DEFAULT 0,
    probe_contract_digest TEXT,
    probe_status TEXT NOT NULL DEFAULT 'unknown',
    last_probed_at TEXT,
    last_error_code TEXT,
    CHECK (structured_output_mode IN ('auto', 'json_schema', 'tool_call', 'json_object', 'prompt_only')),
    CHECK (json_schema_supported IN (0, 1)),
    CHECK (tool_call_supported IN (0, 1)),
    CHECK (json_object_supported IN (0, 1)),
    CHECK (prompt_only_supported IN (0, 1)),
    CHECK (probe_status IN ('unknown', 'passed', 'failed'))
);

CREATE INDEX ix_inference_provider_capabilities_status
ON inference_provider_capabilities (probe_status, profile_id);
