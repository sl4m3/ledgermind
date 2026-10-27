from __future__ import annotations

import json
import subprocess
from pathlib import Path

import ledgermind_local.installer.targets.hermes.adapter as hermes_adapter_module
from ledgermind_local.installer.models import (
    EmbeddingApiConfig,
    EmbeddingConfig,
    GenerationConfig,
    InstallerConfig,
)
from ledgermind_local.installer.paths import InstallerPaths
from ledgermind_local.installer.targets.base import AdapterContext
from ledgermind_local.installer.targets.hermes.adapter import HermesTargetAdapter


def _config() -> InstallerConfig:
    return InstallerConfig(
        semantic_language="en",
        generation=GenerationConfig(
            endpoint="https://provider.example/v1", token="token", model="model"
        ),
        embedding=EmbeddingConfig(
            mode="api",
            api=EmbeddingApiConfig(
                endpoint="https://provider.example/v1",
                token="token",
                model="embedding",
                dimensions=3,
            ),
        ),
    )


def test_hermes_adapter_restores_only_owned_files(tmp_path: Path, monkeypatch) -> None:
    hermes = tmp_path / "hermes"
    (hermes / "plugins").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes))
    enabled = False

    def fake_run(command, **_kwargs):
        nonlocal enabled
        if command[2] == "enable":
            enabled = True
            return subprocess.CompletedProcess(command, 0, "enabled\n", "")
        if command[2] == "disable":
            enabled = False
            return subprocess.CompletedProcess(command, 0, "disabled\n", "")
        output = (
            "enabled      user     0.1.0    ledgermind-hermes\n"
            if enabled
            else "not enabled  user     0.1.0    ledgermind-hermes\n"
        )
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(
        hermes_adapter_module.shutil, "which", lambda _name: "/bin/hermes"
    )
    monkeypatch.setattr(subprocess, "run", fake_run)
    bundle = tmp_path / "bundle" / "integrations" / "hermes" / "plugin"
    bundle.mkdir(parents=True)
    (bundle / "plugin.yaml").write_text(
        "name: ledgermind-hermes\n"
        "provides_hooks:\n"
        "  - pre_llm_call\n"
        "  - pre_tool_call\n"
        "  - post_tool_call\n"
        "  - post_llm_call\n"
        "  - on_session_end\n",
        encoding="utf-8",
    )
    (bundle / "__init__.py").write_text("register = object\n", encoding="utf-8")
    context = AdapterContext(
        config=_config(),
        paths=InstallerPaths(home_override=tmp_path / "install"),
        bundle_root=tmp_path / "bundle",
        discovery=HermesTargetAdapter().discover(),
    )
    adapter = HermesTargetAdapter()
    installed = adapter.install(context)
    assert installed["files"] == 3
    assert installed["activation"] == {"enabled": True, "status": "passed"}
    assert adapter.verify(context)["enabled"] is True
    plugin = hermes / "plugins" / "ledgermind-hermes"
    extra = plugin / "user-notes.txt"
    extra.write_text("keep", encoding="utf-8")
    (plugin / "plugin.yaml").write_text("user changed", encoding="utf-8")
    result = adapter.uninstall(context)
    assert result["skipped_user_changes"] == 1
    assert extra.read_text(encoding="utf-8") == "keep"
    assert (plugin / "plugin.yaml").read_text(encoding="utf-8") == "user changed"
    assert not (plugin / "__init__.py").exists()
    assert not (plugin / "config.json").exists()


def test_hermes_adapter_uses_the_shared_memory_space(
    tmp_path: Path, monkeypatch
) -> None:
    hermes = tmp_path / "hermes"
    (hermes / "plugins").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes))
    monkeypatch.setattr(
        hermes_adapter_module.shutil, "which", lambda _name: "/bin/hermes"
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            "enabled      user     0.1.0    ledgermind-hermes\n",
            "",
        ),
    )
    bundle = tmp_path / "bundle" / "integrations" / "hermes" / "plugin"
    bundle.mkdir(parents=True)
    (bundle / "plugin.yaml").write_text(
        "name: ledgermind-hermes\nprovides_hooks: []\n", encoding="utf-8"
    )
    (bundle / "__init__.py").write_text("register = object\n", encoding="utf-8")
    adapter = HermesTargetAdapter()
    context = AdapterContext(
        config=_config().model_copy(update={"memory_mode": "shared"}),
        paths=InstallerPaths(home_override=tmp_path / "install"),
        bundle_root=tmp_path / "bundle",
        discovery=adapter.discover(),
    )

    adapter.install(context)

    payload = json.loads(
        (hermes / "plugins" / "ledgermind-hermes" / "config.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["memory_space_id"] == "shared-default"
