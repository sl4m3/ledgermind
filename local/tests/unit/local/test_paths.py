"""Tests for ServicePaths and bootstrap directory layout behavior."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ledgermind_local.bootstrap import bootstrap_local_service, initialize_local_layout
from ledgermind_local.config import LocalConfig
from ledgermind_local.paths import ServicePaths


def test_default_home_uses_explicit_constant() -> None:
    os.environ.pop("LEDGERMIND_HOME", None)
    paths = ServicePaths()
    assert paths.home == Path("~/.ledgermind/local").expanduser()


def test_env_home_is_respected_when_not_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = "/tmp/ledgermind-env-home"
    monkeypatch.setenv("LEDGERMIND_HOME", home)
    paths = ServicePaths()
    assert paths.home == Path(home)


def test_explicit_home_has_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LEDGERMIND_HOME", "/tmp/ledgermind-env-home")
    explicit = tmp_path / "explicit"
    paths = ServicePaths(home=explicit)
    assert paths.home == explicit.absolute()
    assert paths.home.is_absolute()


def test_windows_like_path_is_handled_without_posix_assumptions() -> None:
    windows_like = r"C:\Users\test\ledgermind"
    paths = ServicePaths(home=windows_like)
    assert str(paths.home).endswith(r"Users\test\ledgermind")


def test_bootstrap_creates_private_directories(tmp_path: Path) -> None:
    service_dir = tmp_path / "secure"
    paths, _ = bootstrap_local_service(
        home=service_dir,
        config=LocalConfig(config_version=1, semantic_language="ru"),
    )

    assert paths.home.exists()
    assert paths.logs_dir.exists()

    home_mode = paths.home.stat().st_mode & 0o777
    logs_mode = paths.logs_dir.stat().st_mode & 0o777
    assert home_mode <= 0o700
    assert logs_mode <= 0o700


def test_configured_database_path_is_resolved_under_service_home(
    tmp_path: Path,
) -> None:
    paths, _ = bootstrap_local_service(
        home=tmp_path / "secure",
        config=LocalConfig(
            config_version=1,
            semantic_language="ru",
            database_path="state/custom.db",
        ),
    )

    database = paths.resolve_database_path("state/custom.db")
    assert database == paths.home / "state" / "custom.db"
    assert database.is_file()


def test_existing_config_controls_database_path_without_creating_default(
    tmp_path: Path,
) -> None:
    home = tmp_path / "configured"
    home.mkdir()
    config = LocalConfig(
        config_version=1, semantic_language="ru", database_path="state.db"
    )
    (home / "config.json").write_text(config.to_json(), encoding="utf-8")

    paths, resolved, _token = initialize_local_layout(home=home)

    assert resolved.database_path == "state.db"
    assert paths.resolve_database_path("state.db").is_file()
    assert not paths.database_file.exists()
