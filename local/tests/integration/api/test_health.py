"""Health endpoints checks for local service API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ledgermind_local.api.app import create_app
from ledgermind_local.api.dependencies import Settings
from ledgermind_local.service_lock import ServiceLock


def _build_client(
    *,
    database_path: str | Path,
    api_token: str = "test-token",
    service_lock_path: Path | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            application=object(),
            settings=Settings(
                database_path=database_path,
                api_token=api_token,
                service_lock_path=service_lock_path,
            ),
        )
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_live_accessible_without_token() -> None:
    client = _build_client(database_path=":memory:")
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_is_protected() -> None:
    client = _build_client(database_path=":memory:")
    response = client.get("/health/ready")
    assert response.status_code == 401


def test_health_ready_fails_without_service_lock(tmp_path: Path) -> None:
    token = "secret-token"
    client = _build_client(
        database_path=tmp_path / "ready.db",
        api_token=token,
        service_lock_path=tmp_path / "service.lock",
    )
    response = client.get("/health/ready", headers=_auth(token))
    assert response.status_code == 503
    payload = response.json()
    assert payload["ready"] is False
    assert payload["checks"]["service_lock"]["ok"] is False
    assert payload["checks"]["service_lock"]["detail"] == "service lock file is missing"


def test_health_ready_succeeds_when_service_lock_is_held_by_current_process(
    tmp_path: Path,
) -> None:
    token = "secret-token"
    lock_path = tmp_path / "service.lock"
    client = _build_client(
        database_path=tmp_path / "ready.db",
        api_token=token,
        service_lock_path=lock_path,
    )
    with ServiceLock(lock_path=lock_path):
        response = client.get("/health/ready", headers=_auth(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["checks"]["service_lock"]["ok"] is True
    assert payload["checks"]["database_open"]["ok"] is True
    assert payload["checks"]["migrations_applied"]["ok"] is True
    assert payload["checks"]["write_handler"]["ok"] is True


def test_health_details_requires_token() -> None:
    response = _build_client(database_path=":memory:").get("/health/details")
    assert response.status_code == 401


def test_health_details_fails_without_service_lock(tmp_path: Path) -> None:
    token = "secret-token"
    client = _build_client(
        database_path=tmp_path / "ready.db",
        api_token=token,
        service_lock_path=tmp_path / "service.lock",
    )
    response = client.get("/health/details", headers=_auth(token))

    assert response.status_code == 503
    payload = response.json()
    assert payload["ready"] is False
    assert payload["checks"]["service_lock"]["ok"] is False


def test_health_details_succeeds_when_service_lock_is_held_by_current_process(
    tmp_path: Path,
) -> None:
    token = "secret-token"
    lock_path = tmp_path / "service.lock"
    client = _build_client(
        database_path=tmp_path / "ready.db",
        api_token=token,
        service_lock_path=lock_path,
    )
    with ServiceLock(lock_path=lock_path):
        response = client.get("/health/details", headers=_auth(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["checks"]["service_lock"]["ok"] is True
    assert payload["checks"]["database_open"]["ok"] is True
    assert payload["checks"]["migrations_applied"]["ok"] is True
    assert payload["checks"]["write_handler"]["ok"] is True
