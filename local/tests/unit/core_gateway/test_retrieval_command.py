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
