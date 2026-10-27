ALTER TABLE inference_provider_capabilities
    ADD COLUMN profile_fingerprint TEXT NOT NULL DEFAULT '';

ALTER TABLE inference_provider_capabilities
    ADD COLUMN transport TEXT NOT NULL DEFAULT 'openai_compatible';

ALTER TABLE inference_provider_capabilities
    ADD COLUMN model TEXT NOT NULL DEFAULT '';

ALTER TABLE inference_provider_capabilities
    ADD COLUMN detected_capabilities_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE inference_provider_capabilities
    ADD COLUMN probed_at TEXT;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN expires_at TEXT;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN probe_result TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE inference_provider_capabilities
    ADD COLUMN last_error TEXT;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN structured_json_schema INTEGER NOT NULL DEFAULT 0;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN structured_json_object INTEGER NOT NULL DEFAULT 0;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN tool_calling INTEGER NOT NULL DEFAULT 0;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN plain_json_prompt INTEGER NOT NULL DEFAULT 0;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN native_schema_strictness INTEGER NOT NULL DEFAULT 0;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN max_input_tokens_known INTEGER;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN max_output_tokens_known INTEGER;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN supports_batch_embeddings INTEGER NOT NULL DEFAULT 0;

ALTER TABLE inference_provider_capabilities
    ADD COLUMN embedding_max_batch INTEGER;

CREATE INDEX ix_inference_provider_capabilities_fingerprint
ON inference_provider_capabilities (profile_id, profile_fingerprint, expires_at);
