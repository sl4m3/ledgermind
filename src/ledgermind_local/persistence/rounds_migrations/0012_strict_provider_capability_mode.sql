CREATE TABLE inference_provider_capabilities_v12 (
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
    profile_fingerprint TEXT NOT NULL DEFAULT '',
    transport TEXT NOT NULL DEFAULT 'openai_compatible',
    model TEXT NOT NULL DEFAULT '',
    detected_capabilities_json TEXT NOT NULL DEFAULT '{}',
    probed_at TEXT,
    expires_at TEXT,
    probe_result TEXT NOT NULL DEFAULT 'unknown',
    last_error TEXT,
    structured_json_schema INTEGER NOT NULL DEFAULT 0,
    structured_json_object INTEGER NOT NULL DEFAULT 0,
    tool_calling INTEGER NOT NULL DEFAULT 0,
    plain_json_prompt INTEGER NOT NULL DEFAULT 0,
    native_schema_strictness INTEGER NOT NULL DEFAULT 0,
    max_input_tokens_known INTEGER,
    max_output_tokens_known INTEGER,
    supports_batch_embeddings INTEGER NOT NULL DEFAULT 0,
    embedding_max_batch INTEGER,
    CHECK (structured_output_mode IN ('auto', 'strict_json_schema', 'json_schema', 'tool_call', 'json_object', 'prompt_only')),
    CHECK (json_schema_supported IN (0, 1)),
    CHECK (tool_call_supported IN (0, 1)),
    CHECK (json_object_supported IN (0, 1)),
    CHECK (prompt_only_supported IN (0, 1)),
    CHECK (probe_status IN ('unknown', 'passed', 'failed')),
    CHECK (probe_result IN ('unknown', 'passed', 'failed')),
    CHECK (structured_json_schema IN (0, 1)),
    CHECK (structured_json_object IN (0, 1)),
    CHECK (tool_calling IN (0, 1)),
    CHECK (plain_json_prompt IN (0, 1)),
    CHECK (native_schema_strictness IN (0, 1)),
    CHECK (supports_batch_embeddings IN (0, 1))
);

INSERT INTO inference_provider_capabilities_v12 (
    profile_id, structured_output_mode, json_schema_supported,
    tool_call_supported, json_object_supported, prompt_only_supported,
    probe_contract_digest, probe_status, last_probed_at, last_error_code,
    profile_fingerprint, transport, model, detected_capabilities_json,
    probed_at, expires_at, probe_result, last_error,
    structured_json_schema, structured_json_object, tool_calling,
    plain_json_prompt, native_schema_strictness, max_input_tokens_known,
    max_output_tokens_known, supports_batch_embeddings, embedding_max_batch
)
SELECT
    profile_id, structured_output_mode, json_schema_supported,
    tool_call_supported, json_object_supported, prompt_only_supported,
    probe_contract_digest, probe_status, last_probed_at, last_error_code,
    profile_fingerprint, transport, model, detected_capabilities_json,
    probed_at, expires_at, probe_result, last_error,
    structured_json_schema, structured_json_object, tool_calling,
    plain_json_prompt, native_schema_strictness, max_input_tokens_known,
    max_output_tokens_known, supports_batch_embeddings, embedding_max_batch
FROM inference_provider_capabilities;

DROP INDEX ix_inference_provider_capabilities_status;
DROP INDEX ix_inference_provider_capabilities_fingerprint;
DROP TABLE inference_provider_capabilities;
ALTER TABLE inference_provider_capabilities_v12
    RENAME TO inference_provider_capabilities;

CREATE INDEX ix_inference_provider_capabilities_status
ON inference_provider_capabilities (probe_status, profile_id);

CREATE INDEX ix_inference_provider_capabilities_fingerprint
ON inference_provider_capabilities (profile_id, profile_fingerprint, expires_at);
