PRAGMA foreign_keys = OFF;

CREATE TABLE inference_profiles_v2 (
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
    structured_output_preference TEXT NOT NULL DEFAULT 'auto',
    token_parameter TEXT NOT NULL DEFAULT 'max_tokens',
    supports_system_role INTEGER NOT NULL DEFAULT 1,
    supports_seed INTEGER NOT NULL DEFAULT 0,
    extra_body_json TEXT NOT NULL DEFAULT '{}',
    CHECK (provider_kind IN ('openai_compatible', 'google_genai', 'nvidia_nim')),
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

INSERT INTO inference_profiles_v2 (
    profile_id, provider_kind, base_url, model, secret_ref,
    timeout_seconds, max_retries, max_input_tokens, max_output_tokens,
    hypothesis_prompt_version, hypothesis_schema_version,
    merge_prompt_version, merge_schema_version, enabled, created_at,
    updated_at, structured_output_preference, token_parameter,
    supports_system_role, supports_seed, extra_body_json
)
SELECT
    profile_id, provider_kind, base_url, model, secret_ref,
    timeout_seconds, max_retries, max_input_tokens, max_output_tokens,
    hypothesis_prompt_version, hypothesis_schema_version,
    merge_prompt_version, merge_schema_version, enabled, created_at,
    updated_at, structured_output_preference, token_parameter,
    supports_system_role, supports_seed, extra_body_json
FROM inference_profiles;

DROP TABLE inference_profiles;

ALTER TABLE inference_profiles_v2 RENAME TO inference_profiles;

CREATE INDEX ix_inference_profiles_enabled
ON inference_profiles (enabled, profile_id);
