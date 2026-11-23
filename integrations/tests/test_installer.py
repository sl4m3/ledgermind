from __future__ import annotations

import json
import stat
from pathlib import Path

from ledgermind_integrations.cli import main
from ledgermind_integrations.installer import install_hermes, uninstall_hermes


def test_installer_writes_plugin_manifest(tmp_path: Path) -> None:
    target = install_hermes(tmp_path)
    plugin_dir = tmp_path / "ledgermind-hermes"
    assert target == plugin_dir / "plugin.yaml"
    assert "capture_schema_version: 1" in target.read_text(encoding="utf-8")
    assert (plugin_dir / "__init__.py").read_text(encoding="utf-8") == (
        "from ledgermind_integrations.adapters.hermes.plugin_entry import register\n\n"
        '__all__ = ["register"]\n'
    )
    config = json.loads((plugin_dir / "config.json").read_text(encoding="utf-8"))
    assert set(config) == {
        "endpoint",
        "token_file",
        "memory_space_id",
        "source_instance_id",
        "profile_id",
        "state_db_path",
        "spool_dir",
    }
    assert "key" not in json.dumps(config).lower()
    assert stat.S_IMODE(plugin_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((plugin_dir / "config.json").stat().st_mode) == 0o600


def test_uninstaller_is_idempotent_and_does_not_remove_extra_files(tmp_path: Path) -> None:
    install_hermes(tmp_path)
    plugin_dir = tmp_path / "ledgermind-hermes"
    extra = plugin_dir / "user-notes.txt"
    extra.write_text("keep", encoding="utf-8")

    assert uninstall_hermes(tmp_path) is True
    assert extra.read_text(encoding="utf-8") == "keep"
    assert not (plugin_dir / "plugin.yaml").exists()
    assert not (plugin_dir / "__init__.py").exists()
    assert not (plugin_dir / "config.json").exists()
    assert uninstall_hermes(tmp_path) is False


def test_cli_can_install_and_uninstall_hermes(tmp_path: Path) -> None:
    assert main(["install", "hermes", "--destination", str(tmp_path)]) == 0
    assert (tmp_path / "ledgermind-hermes" / "plugin.yaml").exists()
    assert main(["uninstall", "hermes", "--destination", str(tmp_path)]) == 0
    assert not (tmp_path / "ledgermind-hermes" / "plugin.yaml").exists()


def test_installer_supports_custom_config_python_paths_and_clean_uninstall(
    tmp_path: Path,
) -> None:
    extra_one = tmp_path / "env_a" / "site-packages"
    extra_two = tmp_path / "env_b" / "site-packages"
    custom_cfg = {
        "endpoint": "https://memory.example.test",
        "token_file": str(tmp_path / "credentials"),
        "memory_space_id": "cloud-space",
        "source_instance_id": "hermes-cloud-1",
        "profile_id": "generation-operational",
        "state_db_path": str(tmp_path / "state.db"),
        "spool_dir": str(tmp_path / "spool"),
    }

    target = install_hermes(
        tmp_path,
        config=custom_cfg,
        extra_python_paths=[extra_one, extra_two, extra_one],
    )
    plugin_dir = tmp_path / "ledgermind-hermes"
    assert target == plugin_dir / "plugin.yaml"
    assert json.loads((plugin_dir / "config.json").read_text(encoding="utf-8")) == custom_cfg
    init_text = (plugin_dir / "__init__.py").read_text(encoding="utf-8")
    assert f"sys.path.append({str(extra_one)!r})" in init_text
    assert f"sys.path.append({str(extra_two)!r})" in init_text
    assert init_text.count(f"sys.path.append({str(extra_one)!r})") == 1
    assert "sys.path.insert" not in init_text

    # Simulate __pycache__ creation from importing __init__.py before uninstall.
    pycache = plugin_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "__init__.cpython-313.pyc").write_bytes(b"pyc")

    assert uninstall_hermes(tmp_path) is True
    assert not (plugin_dir / "config.json").exists()
    assert not (plugin_dir / "__init__.py").exists()
    assert not plugin_dir.exists()
