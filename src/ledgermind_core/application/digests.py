"""Deterministic digest helpers for LedgerMind core."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from ledgermind_core.domain import AtomContent, ExtractionInfo, SourceReference


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _normalize_rfc3339(value: object) -> object:
    if isinstance(value, list):
        return [_normalize_rfc3339(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_rfc3339(item) for key, item in value.items()}
    if not isinstance(value, str) or "T" not in value:
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return value
    return parsed.isoformat().replace("+00:00", "Z")


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


def canonical_raw_round_body(value: Mapping[str, object] | object) -> bytes:
    """Serialize only `source` and `round` for the RawRound payload digest."""

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        serialized = cast(dict[str, Any], model_dump(mode="json", exclude_none=True))
    else:
        serialized = dict(cast(Mapping[str, object], value))
    round_payload = cast(dict[str, Any], serialized["round"])
    events = cast(list[dict[str, Any]], round_payload["events"])
    canonical_round = {
        **round_payload,
        "events": [
            {
                **event,
                "content": event.get("content", []),
                "final": event.get("final", False),
            }
            for event in events
        ],
    }
    return _canonical_json(
        _normalize_rfc3339(
            {
                "source": serialized["source"],
                "round": canonical_round,
            }
        )
    )


def calculate_raw_round_digest(value: Mapping[str, object] | object) -> str:
    """Calculate the canonical `sha256:<64 hex>` digest for a raw round."""

    return _hash_prefixed(canonical_raw_round_body(value))


def verify_raw_round_digest(value: Mapping[str, object] | object) -> bool:
    """Return whether a request's declared payload digest matches its body."""

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        declared = cast(str, cast(Any, value).payload_digest)
    else:
        declared = cast(str, dict(cast(Mapping[str, object], value))["payload_digest"])
    return declared == calculate_raw_round_digest(value)


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
    "calculate_raw_round_digest",
    "calculate_request_hash",
    "calculate_source_round_key",
    "canonical_raw_round_body",
    "verify_raw_round_digest",
]
