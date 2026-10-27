from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledgermind_local.api.maintenance import create_maintenance_router


class _Runtime:
    def __init__(self) -> None:
        self.requests: list[tuple[int, str | None, str | None]] = []

    def retry_failed_round_semantic(
        self,
        *,
        limit: int,
        error_code: str | None = None,
        memory_space_id: str | None = None,
    ) -> dict[str, object]:
        self.requests.append((limit, error_code, memory_space_id))
        return {
            "status": "completed",
            "error_code": error_code,
            "memory_space_id": memory_space_id,
            "requeued_normalization_commands": 2,
            "retried_failed_round_semantic": 3,
        }


def test_replay_failed_is_authenticated_explicit_and_bounded() -> None:
    runtime = _Runtime()
    app = FastAPI()
    app.include_router(create_maintenance_router(lambda: "test-token", runtime))
    client = TestClient(app)

    response = client.post(
        "/maintenance/replay-failed?limit=5&error_code=provider_capability_unverified"
        "&memory_space_id=codex-default"
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "completed",
        "error_code": "provider_capability_unverified",
        "memory_space_id": "codex-default",
        "requeued_normalization_commands": 2,
        "retried_failed_round_semantic": 3,
    }
    assert runtime.requests == [(5, "provider_capability_unverified", "codex-default")]
    assert client.post("/maintenance/replay-failed?limit=0").status_code == 422
    assert client.post("/maintenance/replay-failed?error_code=%20").status_code == 422
    assert client.post("/maintenance/replay-failed?memory_space_id=%20").status_code == 422
