"""Embedding purpose values accepted by the Local technical boundary."""

from __future__ import annotations

from typing import Literal, TypeAlias

EmbeddingPurpose: TypeAlias = Literal[
    "object_query",
    "subject_query",
    "object_mention",
    "object_card",
    "object_signature",
    "value_record",
    "retrieval_query",
    "facet_catalog",
    "knowledge",
    "object_candidate_query",
    "object_identity_passage",
]

# ``knowledge`` is retained for older Local callers; Core's claim-first wire
# purpose is ``subject_query``.
EMBEDDING_PURPOSES = frozenset(
    {
        "object_query",
        "subject_query",
        "object_mention",
        "object_card",
        "object_signature",
        "value_record",
        "retrieval_query",
        "facet_catalog",
        "knowledge",
        "object_candidate_query",
        "object_identity_passage",
    }
)


def validate_embedding_purpose(value: object) -> EmbeddingPurpose:
    if not isinstance(value, str) or value not in EMBEDDING_PURPOSES:
        raise ValueError("embedding purpose is not supported")
    return value  # type: ignore[return-value]


__all__ = ["EMBEDDING_PURPOSES", "EmbeddingPurpose", "validate_embedding_purpose"]
