"""Authentication checks for local HTTP API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ledgermind_local.api.app import create_app
from ledgermind_local.api.dependencies import Settings


def _build_client(*, database_token: str = "test-token") -> TestClient:
    return TestClient(
        create_app(
            application=object(),
            settings=Settings(database_path=":memory:", api_token=database_token),
        )
    )


def test_health_live_is_accessible_without_token() -> None:
    client = _build_client()
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_live_returns_details_with_token() -> None:
    token = "secret-token"
    client = _build_client(database_token=token)
    response = client.get(
        "/health/live",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["healthy"] is True
    assert payload["database_path"] == ":memory:"


def test_auth_rejects_missing_token_for_protected_route() -> None:
    client = _build_client()
    response = client.get("/ping")
    assert response.status_code == 401


def test_auth_rejects_wrong_token_for_protected_route() -> None:
    client = _build_client(database_token="expected")
    response = client.get(
        "/ping",
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_auth_allows_correct_token_for_protected_route() -> None:
    token = "correct-token"
    client = _build_client(database_token=token)
    response = client.get(
        "/ping",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"pong": "true"}


def test_query_token_does_not_open_protected_endpoint() -> None:
    token = "queryless"
    client = _build_client(database_token=token)
    response = client.get(f"/ping?api_token={token}")
    assert response.status_code == 401


def test_versioned_routes_are_not_compatibility_aliases() -> None:
    client = _build_client()
    prefix = "/" + "v" + "1"
    for route in (
        prefix + "/ping",
        prefix + "/rounds",
        prefix + "/context/retrieve",
        prefix + "/health/ready",
    ):
        assert client.get(route, headers={"Authorization": "Bearer test-token"}).status_code == 404


def test_create_app_does_not_create_database_file(tmp_path) -> None:
    database = tmp_path / "local.db"
    assert not database.exists()
    _ = create_app(
        application=object(),
        settings=Settings(database_path=database, api_token="x"),
    )
    assert not database.exists()
