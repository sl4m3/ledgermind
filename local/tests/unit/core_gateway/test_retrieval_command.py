from __future__ import annotations

import pytest
from ledgermind_local.core_gateway.contracts import RetrieveContextCommand


def _command(**overrides: object) -> RetrieveContextCommand:
    values: dict[str, object] = {
        "request_id": "request-1",
        "memory_space_id": "space",
        "query_text": "continue",
        "query_embedding": (0.1, 0.2),
    }
    values.update(overrides)
    return RetrieveContextCommand(**values)  # type: ignore[arg-type]


def test_retrieval_command_forwards_request_time_and_scoped_schema() -> None:
    command = _command(
        request_time="2026-10-31T12:00:00Z",
        semantic_delivery=True,
        scoped_dependencies=True,
    )
    payload = command.to_payload()
    assert payload["schema_version"] == 5
    assert payload["request_time"] == "2026-10-31T12:00:00Z"


def test_retrieval_command_rejects_blank_request_time() -> None:
    with pytest.raises(ValueError, match="request_time"):
        _command(request_time=" ")


def test_candidate_policy_is_forwarded_only_for_semantic_delivery() -> None:
    scoped = _command(
        semantic_delivery=True,
        scoped_dependencies=True,
        candidate_policy="semantic",
    )
    assert scoped.to_payload()["schema_version"] == 5
    assert scoped.to_payload()["candidate_policy"] == "semantic"

    legacy = _command(candidate_policy="semantic")
    assert legacy.to_payload()["schema_version"] == 2
    assert "candidate_policy" not in legacy.to_payload()


def test_candidate_policy_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="candidate_policy"):
        _command(candidate_policy="lexical")
