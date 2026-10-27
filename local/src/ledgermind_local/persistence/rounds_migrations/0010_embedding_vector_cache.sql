CREATE TABLE IF NOT EXISTS embedding_vector_cache (
    cache_key TEXT PRIMARY KEY,
    profile_fingerprint TEXT NOT NULL,
    cache_namespace TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    vector_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_embedding_vector_cache_profile
ON embedding_vector_cache (profile_fingerprint, cache_namespace, content_digest);
