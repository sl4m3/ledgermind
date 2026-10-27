"""Canonical provider-secret references shared with the Local runtime."""

GENERATION_SECRET_REF = "generation-api"
EMBEDDING_SECRET_REF = "embedding-api"
LOCAL_EMBEDDING_SECRET_REF = "embedding-local"
RERANKER_SECRET_REF = "reranker-api"

# Releases predating the Local inference boundary used slash-separated JSON
# keys. Keep them readable for import and cleanup, but do not write them into
# new runtime profiles because Local intentionally accepts identifier refs.
LEGACY_GENERATION_SECRET_REF = "generation/token"
LEGACY_EMBEDDING_SECRET_REF = "embedding/token"

__all__ = [
    "EMBEDDING_SECRET_REF",
    "GENERATION_SECRET_REF",
    "LEGACY_EMBEDDING_SECRET_REF",
    "LEGACY_GENERATION_SECRET_REF",
    "LOCAL_EMBEDDING_SECRET_REF",
    "RERANKER_SECRET_REF",
]
