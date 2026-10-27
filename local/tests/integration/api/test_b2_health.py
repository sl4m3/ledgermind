"""B2 health/readiness endpoint semantics."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ledgermind_local.api.app import create_app
from ledgermind_local.api.dependencies import Settings
from ledgermind_local.bootstrap import LocalRuntime
from ledgermind_local.config import LocalConfig, WorkerSetConfig
from ledgermind_local.paths import ServicePaths


def _runtime(tmp_path: Path) -> LocalRuntime:
    paths = ServicePaths(tmp_path / "local")
    config = LocalConfig(
        config_version=1,
        semantic_language="ru",
        workers=WorkerSetConfig(
            retention={"enabled": False},
            core_commands={"enabled": False},
            core_model_tasks={"enabled": False},
        ),
    )
    runtime = LocalRuntime(
        paths=paths,
        config=config,
        api_token="test-token",
        core_gateway_factory=lambda: (_ for _ in ()).throw(RuntimeError("daemon unavailable")),
    )
    runtime.start()
    return runtime


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_capture_ready_is_independent_from_full_ready(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    try:
        client = TestClient(
            create_app(
                application=runtime,
                settings=Settings(
                    rounds_database_path=runtime.database_path,
                    api_token="test-token",
                    service_lock_path=runtime.paths.service_lock_file,
                ),
            )
        )
        capture = client.get("/health/capture-ready", headers=_auth())
        full = client.get("/health/full-ready", headers=_auth())
        ready = client.get("/health/ready", headers=_auth())
        details = client.get("/health/details", headers=_auth())

        assert capture.status_code == 200
        assert capture.json()["ready"] is True
        assert capture.json()["capture_ready"] is True
        assert capture.json()["full_ready"] is False
        assert full.status_code == 503
        assert full.json()["ready"] is False
        assert ready.status_code == 503
        assert details.status_code == 200
        assert details.json()["capture_ready"] is True
        assert details.json()["full_ready"] is False
        assert "database_path" not in details.json()
    finally:
        runtime.stop()


def test_runtime_stop_releases_pid_and_lock(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    pid_path = runtime.paths.service_pid_file
    lock_path = runtime.paths.service_lock_file
    assert pid_path.exists()
    assert lock_path.exists()
    runtime.stop()
    assert not pid_path.exists()
    assert not lock_path.exists()


def test_runtime_activity_is_authenticated_and_fails_closed(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    try:
        client = TestClient(
            create_app(
                application=runtime,
                settings=Settings(
                    rounds_database_path=runtime.database_path,
                    api_token="test-token",
                    service_lock_path=runtime.paths.service_lock_file,
                ),
            )
        )

        assert client.get("/runtime/activity").status_code == 401
        response = client.get("/runtime/activity", headers=_auth())

        assert response.status_code == 200
        assert response.json()["schema_version"] == 1
        assert response.json()["known"] is False
        assert response.json()["quiescent"] is False
    finally:
        runtime.stop()
