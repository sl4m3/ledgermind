"""Tests for ledgermind install hermes command."""
import sys
import os
import json
import io
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def run_cli(args, fake_home=None):
    """Helper to run the ledgermind CLI."""
    from ledgermind.server.cli import main
    from ledgermind.server import installers

    stdout = io.StringIO()
    stderr = io.StringIO()

    # Patch installer constants to use fake home
    patches = []
    if fake_home:
        patches.append(patch.object(installers, "HERMES_HOME", fake_home / ".hermes"))
        patches.append(patch.object(installers, "HERMES_PLUGINS_DIR", fake_home / ".hermes" / "plugins"))
        patches.append(patch.object(installers, "HERMES_CONFIG", fake_home / ".hermes" / "config.yaml"))
        patches.append(patch.object(installers, "LEDGERMIND_HOME", fake_home / ".ledgermind" / "hermes"))
        patches.append(patch.object(Path, "home", lambda: fake_home))

    with patch.object(sys, "argv", ["ledgermind"] + args):
        with patch.object(sys, "stdout", stdout):
            with patch.object(sys, "stderr", stderr):
                for p in patches:
                    p.start()
                try:
                    main()
                    return_code = 0
                except SystemExit as e:
                    return_code = e.code if isinstance(e.code, int) else 0
                except Exception as e:
                    stderr.write(str(e))
                    return_code = 1
                finally:
                    for p in patches:
                        p.stop()

    class Result:
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    return Result(stdout.getvalue(), stderr.getvalue(), return_code)


@pytest.fixture
def hermes_home(tmp_path):
    """Create a fake Hermes home directory."""
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()

    # Create minimal config.yaml
    config_yaml = hermes_dir / "config.yaml"
    config_yaml.write_text("plugins:\n  enabled: []\n")

    return hermes_dir


@pytest.fixture
def ledgermind_home(tmp_path):
    """Create a fake LedgerMind home directory."""
    lm_dir = tmp_path / ".ledgermind"
    lm_dir.mkdir()
    return lm_dir


class TestInstallHelp:
    def test_install_help(self):
        result = run_cli(["install", "--help"])
        assert result.returncode == 0
        assert "install" in result.stdout.lower() or "hermes" in result.stdout.lower()


class TestInstallWithFlags:
    def test_install_hermes_with_all_flags(self, hermes_home, ledgermind_home, tmp_path):
        """Test install with all flags provided."""
        result = run_cli([
            "install", "hermes",
            "--mode", "agent",
            "--enrichment", "openrouter",
            "--api-key", "test-key-123",
        ], fake_home=tmp_path)

        assert result.returncode == 0
        assert "Done" in result.stderr or "installed" in result.stderr.lower()

        # Check plugin files created
        plugin_dir = hermes_home / "plugins" / "ledgermind"
        assert plugin_dir.exists()
        assert (plugin_dir / "plugin.yaml").exists()
        assert (plugin_dir / "__init__.py").exists()
        assert (plugin_dir / "config.json").exists()
        assert (plugin_dir / ".env").exists()

        # Check .env has API key
        env_content = (plugin_dir / ".env").read_text()
        assert "LEDGERMIND_API_KEY=test-key-123" in env_content

        # Check LedgerMind config
        lm_config = ledgermind_home / "hermes" / "config.json"
        assert lm_config.exists()
        config = json.loads(lm_config.read_text())
        assert config["default_mode"] == "agent"
        assert config["enrichment"]["provider"] == "openrouter"
        assert "api_key" not in config["enrichment"]

    def test_install_hermes_core_mode(self, hermes_home, ledgermind_home, tmp_path):
        """Test install with core mode."""
        result = run_cli([
            "install", "hermes",
            "--mode", "core",
            "--enrichment", "nvidia",
            "--api-key", "nvapi-test",
        ], fake_home=tmp_path)

        assert result.returncode == 0

        lm_config = ledgermind_home / "hermes" / "config.json"
        config = json.loads(lm_config.read_text())
        assert config["default_mode"] == "core"
        assert config["enrichment"]["provider"] == "nvidia"
        assert config["enrichment"]["base_url"] == "https://integrate.api.nvidia.com/v1"

    def test_install_hermes_custom_base_url(self, hermes_home, ledgermind_home, tmp_path):
        """Test install with custom base URL."""
        result = run_cli([
            "install", "hermes",
            "--enrichment", "custom",
            "--base-url", "http://localhost:8080/v1",
        ], fake_home=tmp_path)

        assert result.returncode == 0

        plugin_config = hermes_home / "plugins" / "ledgermind" / "config.json"
        config = json.loads(plugin_config.read_text())
        assert config["base_url"] == "http://localhost:8080/v1"


class TestInstallNoHermes:
    def test_install_fails_without_hermes(self, tmp_path):
        """Test install fails when Hermes is not installed."""
        result = run_cli(["install", "hermes", "--api-key", "test"], fake_home=tmp_path)

        assert result.returncode == 1
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()


class TestPluginFiles:
    def test_plugin_yaml_content(self, hermes_home, tmp_path):
        """Test plugin.yaml has correct content."""
        run_cli(["install", "hermes", "--api-key", "test"], fake_home=tmp_path)

        plugin_yaml = hermes_home / "plugins" / "ledgermind" / "plugin.yaml"
        content = plugin_yaml.read_text()

        assert "name: ledgermind" in content
        assert "pre_llm_call" in content
        assert "post_llm_call" in content
        assert "on_session_start" in content

    def test_plugin_init_has_required_functions(self, hermes_home, tmp_path):
        """Test __init__.py has all required functions."""
        run_cli(["install", "hermes", "--api-key", "test"], fake_home=tmp_path)

        init_file = hermes_home / "plugins" / "ledgermind" / "__init__.py"
        content = init_file.read_text()

        assert "def _on_pre_llm_call" in content
        assert "def _on_post_llm_call" in content
        assert "def _on_session_start" in content
        assert "def _import_state_db" in content
        assert "def _read_state_db" in content
        assert "def _call_enrichment_model" in content
        assert "def register(ctx)" in content

    def test_plugin_config_json(self, hermes_home, tmp_path):
        """Test plugin config.json is valid and .env exists."""
        run_cli(["install", "hermes", "--api-key", "key123", "--enrichment", "openrouter"], fake_home=tmp_path)

        config_file = hermes_home / "plugins" / "ledgermind" / "config.json"
        config = json.loads(config_file.read_text())

        assert config["provider"] == "openrouter"
        assert "api_key" not in config
        assert "base_url" in config

        env_file = hermes_home / "plugins" / "ledgermind" / ".env"
        assert env_file.exists()
        assert "LEDGERMIND_API_KEY=key123" in env_file.read_text()
        assert "model" in config


class TestHermesConfigUpdated:
    def test_plugin_enabled_in_hermes_config(self, hermes_home, tmp_path):
        """Test plugin is added to Hermes config.yaml."""
        run_cli(["install", "hermes", "--api-key", "test"], fake_home=tmp_path)

        config_yaml = hermes_home / "config.yaml"
        content = config_yaml.read_text()

        assert "ledgermind" in content

    def test_plugin_not_duplicated(self, hermes_home, tmp_path):
        """Test running install twice doesn't duplicate plugin."""
        run_cli(["install", "hermes", "--api-key", "test"], fake_home=tmp_path)
        run_cli(["install", "hermes", "--api-key", "test"], fake_home=tmp_path)

        config_yaml = hermes_home / "config.yaml"
        content = config_yaml.read_text()
        assert content.count("ledgermind") == 1
