"""Deterministic digest helpers for LedgerMind core."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from domain import AtomContent, ExtractionInfo, SourceReference


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash_prefixed(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def calculate_source_round_key(source: SourceReference | Mapping[str, str]) -> str:
    if isinstance(source, SourceReference):
        fields = source.source_round_key_data
    else:
        fields = (
            source["source_system"],
            source["source_instance_id"],
            source["source_profile_id"],
            source["source_session_id"],
            source["source_round_id"],
        )

    canonical = "\n".join(fields).encode("utf-8")
    return _hash_prefixed(canonical)


def calculate_request_hash(request: Mapping[str, object]) -> str:
    return _hash_prefixed(_canonical_json(request))


def calculate_idempotency_key(
    source_round_key: str,
    extraction_prompt_version: int,
    extraction_schema_version: int,
) -> str:
    return _hash_prefixed(
        _canonical_json(
            {
                "source_round_key": source_round_key,
                "prompt_version": extraction_prompt_version,
                "schema_version": extraction_schema_version,
            }
        )
    )


def calculate_atom_content_digest(
    content: AtomContent,
    source: SourceReference,
    extraction: ExtractionInfo,
) -> str:
    return _hash_prefixed(
        _canonical_json(
            {
                "content": {
                    "title": content.title,
                    "target": content.target,
                    "statement": content.statement,
                    "rationale": content.rationale,
                    "result": content.result,
                    "artifacts": list(content.artifacts),
                },
                "source": {
                    "source_system": source.source_system,
                    "source_instance_id": source.source_instance_id,
                    "source_profile_id": source.source_profile_id,
                    "source_session_id": source.source_session_id,
                    "source_round_id": source.source_round_id,
                    "first_message_id": source.first_message_id,
                    "final_message_id": source.final_message_id,
                    "message_ids": list(source.message_ids),
                    "source_digest": source.source_digest,
                    "source_schema_version": source.source_schema_version,
                    "resolver_version": source.resolver_version,
                },
                "extraction": {
                    "host": extraction.host,
                    "provider": extraction.provider,
                    "model": extraction.model,
                    "prompt_version": extraction.prompt_version,
                    "schema_version": extraction.schema_version,
                    "purpose": extraction.purpose,
                },
            }
        )
    )


__all__ = [
    "calculate_atom_content_digest",
    "calculate_idempotency_key",
    "calculate_request_hash",
    "calculate_source_round_key",
]
