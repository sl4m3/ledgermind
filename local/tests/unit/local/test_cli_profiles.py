from __future__ import annotations

import sqlite3
from io import StringIO

from ledgermind_local.cli import main
from ledgermind_local.inference import SecretStore
from ledgermind_local.paths import ServicePaths


def _add(home, profile_id: str, secret_ref: str = "provider-main") -> int:
    if not ServicePaths(home).config_file.exists():
        assert (
            main(
                [
                    "--home",
                    str(home),
                    "init",
                    "--semantic-language",
                    "ru",
                ]
            )
            == 0
        )
    return main(
        [
            "--home",
            str(home),
            "profiles",
            "add",
            "--id",
            profile_id,
            "--provider",
            "openai_compatible",
            "--base-url",
            "https://provider.example/v1",
            "--model",
            "model",
            "--secret-ref",
            secret_ref,
        ]
    )


def test_profiles_add_and_list_do_not_print_secret_values(tmp_path, capsys) -> None:
    home = tmp_path / "local"
    assert _add(home, "operational-default") == 0
    output = capsys.readouterr().out
    assert "operational-default" in output
    assert "provider-main" in output
    assert "TOP_SECRET" not in output

    assert main(["--home", str(home), "profiles", "list"]) == 0
    output = capsys.readouterr().out
    assert "operational-default" in output
    assert "secret_ref" in output


def test_profiles_bind_slots_and_remove(tmp_path) -> None:
    home = tmp_path / "local"
    assert _add(home, "operational-default") == 0
    assert _add(home, "background-default", "provider-background") == 0
    database = ServicePaths(home).rounds_database_file
    connection = sqlite3.connect(database)
    connection.execute(
        "INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("space", "tests", "2026-08-03T00:00:00Z", "2026-08-03T00:00:00Z"),
    )
    connection.commit()
    connection.close()

    assert (
        main(
            [
                "--home",
                str(home),
                "inference",
                "bind",
                "--memory-space-id",
                "space",
                "--slot",
                "operational",
                "--profile-id",
                "operational-default",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--home",
                str(home),
                "inference",
                "bind",
                "--memory-space-id",
                "space",
                "--slot",
                "background",
                "--profile-id",
                "background-default",
            ]
        )
        == 0
    )
    connection = sqlite3.connect(database)
    row = connection.execute(
        "SELECT profile_slot, profile_id FROM memory_space_model_profiles "
        "WHERE memory_space_id = ? ORDER BY profile_slot",
        ("space",),
    ).fetchone()
    assert row == ("background", "background-default")
    rows = connection.execute(
        "SELECT profile_slot, profile_id FROM memory_space_model_profiles "
        "WHERE memory_space_id = ? ORDER BY profile_slot",
        ("space",),
    ).fetchall()
    assert rows == [
        ("background", "background-default"),
        ("operational", "operational-default"),
    ]
    connection.execute(
        "DELETE FROM memory_space_model_profiles "
        "WHERE memory_space_id = ? AND profile_slot = ?",
        ("space", "background"),
    )
    connection.commit()
    connection.close()

    assert (
        main(
            ["--home", str(home), "profiles", "remove", "--id", "background-default"]
        )
        == 0
    )


def test_secrets_cli_reads_stdin_and_never_prints_secret_value(
    tmp_path, monkeypatch, capsys
) -> None:
    home = tmp_path / "local"
    assert (
        main(["--home", str(home), "init", "--semantic-language", "ru"]) == 0
    )
    monkeypatch.setattr("sys.stdin", StringIO("TOP_SECRET\n"))
    assert (
        main(
            [
                "--home",
                str(home),
                "secrets",
                "set",
                "--ref",
                "provider-main",
                "--value-stdin",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "provider-main" in output
    assert "TOP_SECRET" not in output

    paths = ServicePaths(home)
    assert (
        SecretStore(paths.resolve_home_path("secrets.json")).get("provider-main")
        == "TOP_SECRET"
    )

    assert main(["--home", str(home), "secrets", "list"]) == 0
    output = capsys.readouterr().out
    assert "provider-main" in output
    assert "TOP_SECRET" not in output

    assert (
        main(["--home", str(home), "secrets", "delete", "--ref", "provider-main"]) == 0
    )
