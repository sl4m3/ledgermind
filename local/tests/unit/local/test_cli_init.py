"""Tests for `ledgermind init` behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from ledgermind_local import bootstrap
from ledgermind_local.cli import main
from ledgermind_local.config import LocalConfig


def _run_init(home: Path, *args: str) -> int:
    return main(
        ["--home", str(home), "init", "--semantic-language", "ru", *args]
    )


def test_init_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "service"
    code = _run_init(home)
    assert code == 0
    first_token = (home / "server.token").read_text(encoding="utf-8")
    config = (home / "config.json").read_text(encoding="utf-8")
    assert first_token not in config
    assert "token" not in config

    code = _run_init(home)
    assert code == 0
    second_token = (home / "server.token").read_text(encoding="utf-8")
    assert second_token == first_token
    assert (home / "rounds.db").exists()
    assert (home / "config.json").exists()


def test_init_force_does_not_rotate_token_without_rotate_flag(tmp_path: Path) -> None:
    home = tmp_path / "service"
    code = _run_init(home)
    assert code == 0
    token_before = (home / "server.token").read_text(encoding="utf-8")

    code = _run_init(home, "--force")
    assert code == 0
    token_after = (home / "server.token").read_text(encoding="utf-8")
    assert token_after == token_before


def test_init_rotates_token_with_force_and_rotate_flag(tmp_path: Path) -> None:
    home = tmp_path / "service"
    code = _run_init(home)
    assert code == 0
    token_before = (home / "server.token").read_text(encoding="utf-8")

    code = _run_init(home, "--force", "--rotate-token")
    assert code == 0
    token_after = (home / "server.token").read_text(encoding="utf-8")
    assert token_after != token_before


def test_init_rotate_token_requires_force(tmp_path: Path) -> None:
    home = tmp_path / "service"
    assert _run_init(home) == 0
    assert main(["--home", str(home), "init", "--rotate-token"]) == 2


def test_token_file_has_private_permissions_on_posix(tmp_path: Path) -> None:
    home = tmp_path / "service"
    code = _run_init(home)
    assert code == 0

    mode = (home / "server.token").stat().st_mode & 0o777
    assert mode == 0o600


def test_existing_token_is_canonicalized_without_trailing_whitespace(
    tmp_path: Path,
) -> None:
    home = tmp_path / "service"
    home.mkdir()
    (home / "server.token").write_text("  preproduction-token\n", encoding="utf-8")

    _paths, _config, token = bootstrap.initialize_local_layout(
        home=home,
        config=LocalConfig(config_version=1, semantic_language="ru"),
    )

    assert token == "preproduction-token"
    assert (home / "server.token").read_text(encoding="utf-8") == "preproduction-token"


def test_partial_failure_does_not_create_empty_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "service"
    code = _run_init(home)
    assert code == 0
    original_token = (home / "server.token").read_text(encoding="utf-8")

    def fail_write(path: Path, data: str, mode: int) -> None:
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(bootstrap, "_atomic_write_text", fail_write)
    with pytest.raises(RuntimeError):
        _run_init(home, "--force", "--rotate-token")

    token_after = (home / "server.token").read_text(encoding="utf-8")
    assert token_after == original_token
    assert token_after
