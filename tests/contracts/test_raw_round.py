from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ledgermind_core.application.digests import (
    calculate_raw_round_digest,
    verify_raw_round_digest,
)
from ledgermind_core.contracts import RawRoundRequest

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "raw_round_v2" / "hermes_complete.json"
_SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "raw-round-v2.schema.json"


def test_raw_round_fixture_matches_contract_and_digest() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    request = RawRoundRequest.model_validate(payload)

    assert verify_raw_round_digest(request) is True
    assert calculate_raw_round_digest(request) == payload["payload_digest"]
    assert [event.kind for event in request.round.events] == [
        "message",
        "tool_call",
        "message",
    ]


def test_raw_round_contract_forbids_unknown_and_semantic_fields() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    payload["hypothesis"] = {"statement": "must not be client supplied"}

    with pytest.raises(ValidationError):
        RawRoundRequest.model_validate(payload)

    dumped = RawRoundRequest.model_validate(
        json.loads(_FIXTURE.read_text(encoding="utf-8"))
    ).model_dump(mode="json")
    assert "hypothesis" not in dumped
    assert "title" not in dumped
    assert "phase" not in dumped
    assert "confidence" not in dumped


def test_raw_round_digest_covers_tool_event_details() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    request = RawRoundRequest.model_validate(payload)
    changed = request.model_dump(mode="json")
    changed["round"]["events"][1]["arguments"] = {"path": "different.md"}
    changed["payload_digest"] = payload["payload_digest"]

    assert verify_raw_round_digest(changed) is False


def test_schema_is_strict_and_namespaced() -> None:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert schema["properties"]["api_version"]["const"] == "2"
    assert schema["$defs"]["source"]["properties"]["system"]["type"] == "string"
    assert "extensions" in schema["$defs"]
