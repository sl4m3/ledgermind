from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledgermind_protocol import (
    RawRoundValidationError,
    calculate_payload_digest,
    validate_raw_round,
)

_ROOT = Path(__file__).resolve().parents[3]


def test_public_valid_fixture_round_trips() -> None:
    payload = json.loads(
        (_ROOT / "conformance" / "valid" / "simple_round.json").read_text(encoding="utf-8")
    )
    request = validate_raw_round(payload)
    assert request.schema_version == 2
    assert request.idempotency_key == request.payload_digest
    assert calculate_payload_digest(request) == request.payload_digest


@pytest.mark.parametrize(
    "fixture_name",
    ["tool_role_message.json", "tool_result_without_call.json", "digest_mismatch.json"],
)
def test_public_invalid_fixtures_are_rejected(fixture_name: str) -> None:
    payload = json.loads(
        (_ROOT / "conformance" / "invalid" / fixture_name).read_text(encoding="utf-8")
    )
    with pytest.raises(RawRoundValidationError):
        validate_raw_round(payload)
