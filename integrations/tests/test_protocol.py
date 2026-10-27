from __future__ import annotations

import json
from pathlib import Path

import pytest
from ledgermind_protocol import (
    RawRoundValidationError,
    calculate_payload_digest,
    validate_raw_round,
)

_FIXTURE = Path(__file__).resolve().parents[2] / "conformance" / "valid" / "hermes_complete.json"


def test_fixture_has_the_same_digest_as_public_protocol() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert calculate_payload_digest(payload) == payload["payload_digest"]
    assert validate_raw_round(payload).source.event_ids == ["1001", "1002", "1003"]


def test_client_rejects_semantic_fields_and_unknown_fields() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    for field in ("hypothesis", "title", "statement", "rationale", "phase", "confidence"):
        candidate = dict(payload)
        candidate[field] = "not client owned"
        with pytest.raises(RawRoundValidationError):
            validate_raw_round(candidate)


def test_digest_covers_observed_tool_arguments() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    changed = json.loads(json.dumps(payload))
    changed["round"]["events"][1]["arguments"]["path"] = "other.md"
    assert calculate_payload_digest(changed) != payload["payload_digest"]
