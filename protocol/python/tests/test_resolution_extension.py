from __future__ import annotations

import copy

import pytest

from ledgermind_protocol import (
    RawRoundValidationError,
    build_resolution_extension,
    calculate_payload_digest,
    validate_raw_round,
    with_payload_digest,
)


def _payload() -> dict[str, object]:
    return with_payload_digest(
        {
            "schema_version": 2,
            "idempotency_key": "sha256:" + "0" * 64,
            "memory_space_id": "space-1",
            "source": {
                "system": "hermes",
                "instance_id": "instance-1",
                "profile_id": "default",
                "session_id": "session-1",
                "round_id": "round-1",
                "first_event_id": "user-1",
                "final_event_id": "assistant-1",
                "event_ids": ["user-1", "assistant-1"],
                "source_schema_version": 1,
                "adapter_version": "test/1",
                "extensions": {
                    "vendor.example": {"kept": True},
                    "ledgermind_resolution": build_resolution_extension("session-1"),
                },
            },
            "round": {
                "started_at": "2026-08-10T10:00:00Z",
                "completed_at": "2026-08-10T10:00:01Z",
                "events": [
                    {
                        "event_id": "user-1",
                        "sequence": 0,
                        "kind": "message",
                        "role": "user",
                        "content": [{"type": "text", "text": "hello"}],
                    },
                    {
                        "event_id": "assistant-1",
                        "sequence": 1,
                        "kind": "message",
                        "role": "assistant",
                        "final": True,
                        "content": [{"type": "text", "text": "done"}],
                    },
                ],
            },
        }
    )


def test_resolution_is_source_owned_digest_covered_and_unrelated_extensions_survive() -> None:
    payload = _payload()
    request = validate_raw_round(payload)

    assert request.source.extensions is not None
    assert request.source.extensions["vendor.example"] == {"kept": True}
    resolution = request.source.extensions["ledgermind_resolution"]
    assert resolution["conversation_id"] == "session-1"
    assert resolution["task_id"] is None

    changed = copy.deepcopy(payload)
    changed["source"]["extensions"]["ledgermind_resolution"]["conversation_id"] = "session-2"  # type: ignore[index]
    assert calculate_payload_digest(changed) != payload["payload_digest"]


@pytest.mark.parametrize(
    "resolution",
    [
        None,
        {"schema_version": 2, "project_id": None, "repository_id": None, "task_id": None, "conversation_id": "s"},
        {"schema_version": 1, "project_id": None, "repository_id": None, "task_id": None, "conversation_id": "s", "extra": "nope"},
    ],
)
def test_malformed_owned_source_extension_is_rejected(resolution: object) -> None:
    payload = _payload()
    payload["source"]["extensions"]["ledgermind_resolution"] = resolution  # type: ignore[index]
    payload = with_payload_digest(payload)

    with pytest.raises(RawRoundValidationError):
        validate_raw_round(payload)


def test_resolution_mapper_uses_git_root_and_never_round_as_task(tmp_path) -> None:
    repository = tmp_path / "repository"
    nested = repository / "src" / "component"
    nested.mkdir(parents=True)
    (repository / ".git").mkdir()

    resolution = build_resolution_extension(
        "session-real",
        metadata={"working_directory": str(nested)},
    )

    assert resolution == {
        "schema_version": 1,
        "project_id": None,
        "repository_id": repository.resolve().as_posix(),
        "task_id": None,
        "conversation_id": "session-real",
    }


def test_resolution_mapper_does_not_choose_between_conflicting_repositories(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / ".git").mkdir()
    (second / ".git").mkdir()

    resolution = build_resolution_extension(
        "session-real",
        metadata=[
            {"working_directory": str(first)},
            {"working_directory": str(second)},
        ],
    )

    assert resolution["repository_id"] is None
    assert resolution["project_id"] is None
    assert resolution["task_id"] is None
