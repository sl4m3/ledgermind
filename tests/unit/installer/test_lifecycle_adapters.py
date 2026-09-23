from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledgermind_local.installer.models import (
    EmbeddingApiConfig,
    EmbeddingConfig,
    GenerationConfig,
    InstallerConfig,
)
from ledgermind_local.installer.paths import InstallerPaths
from ledgermind_local.installer.targets.base import AdapterContext
from ledgermind_local.installer.targets.lifecycle import (
    PLUGIN_SPECS,
    SPECS,
    LifecycleTargetAdapter,
    PluginTargetAdapter,
)
from ledgermind_local.installer.targets.registry import target_ids


def _config() -> InstallerConfig:
    return InstallerConfig(
        semantic_language="en",
        generation=GenerationConfig(
            endpoint="https://provider.example/v1",
            token="token",
            model="model",
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


@pytest.mark.parametrize("spec", SPECS, ids=lambda spec: spec.target_id)
def test_command_adapter_preserves_user_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spec
) -> None:
    home = tmp_path / spec.target_id
    home.mkdir()
    monkeypatch.setenv(spec.env_home, str(home))
    config_path = home / spec.config_name
    config_path.write_text(
        json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "user-hook"}]}]}}),
        encoding="utf-8",
    )
    adapter = LifecycleTargetAdapter(spec)
    context = AdapterContext(
        config=_config(),
        paths=InstallerPaths(home_override=tmp_path / "install"),
        discovery=adapter.discover(),
    )

    adapter.install(context)
    assert adapter.verify(context)["status"] == "passed"
    runtime_config = context.paths.integrations_dir / spec.target_id / "config.json"
    first_instance = json.loads(runtime_config.read_text(encoding="utf-8"))[
        "source_instance_id"
    ]
    adapter.repair(context)
    assert json.loads(runtime_config.read_text(encoding="utf-8"))[
        "source_instance_id"
    ] == first_instance
    installed = config_path.read_text(encoding="utf-8")
    assert "user-hook" in installed
    assert installed.count("integration-hook") == len(spec.events)
    if spec.target_id == "codex":
        payload = json.loads(installed)
        prompt_handler = payload["hooks"]["UserPromptSubmit"][-1]["hooks"][0]
        stop_handler = payload["hooks"]["Stop"][-1]["hooks"][0]
        assert prompt_handler["timeout"] == 60
        assert stop_handler["timeout"] == 600
        assert stop_handler["async"] is True

    adapter.uninstall(context)
    restored = config_path.read_text(encoding="utf-8")
    assert "user-hook" in restored
    assert "integration-hook" not in restored


@pytest.mark.parametrize("spec", PLUGIN_SPECS, ids=lambda spec: spec.target_id)
def test_plugin_adapter_installs_signed_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spec
) -> None:
    home = tmp_path / spec.target_id
    home.mkdir()
    monkeypatch.setenv(spec.env_home, str(home))
    bundle = tmp_path / "bundle" / "integrations" / spec.target_id / "plugin"
    bundle.mkdir(parents=True)
    if spec.target_id == "opencode":
        (bundle / "ledgermind.js").write_text(
            'const a="__LEDGERMIND_COMMAND__"; const b="__LEDGERMIND_CONFIG__";',
            encoding="utf-8",
        )
    else:
        for name in ("index.js", "package.json", "openclaw.plugin.json"):
            (bundle / name).write_text(
                '{"path":"__LEDGERMIND_CONFIG__"}' if name.endswith(".json") else 'const p="__LEDGERMIND_CONFIG__";',
                encoding="utf-8",
            )
    adapter = PluginTargetAdapter(spec)
    context = AdapterContext(
        config=_config().model_copy(update={"memory_mode": "shared"}),
        paths=InstallerPaths(home_override=tmp_path / "install"),
        bundle_root=tmp_path / "bundle",
        discovery=adapter.discover(),
    )

    adapter.install(context)
    assert adapter.verify(context)["status"] == "passed"
    runtime_config = context.paths.integrations_dir / spec.target_id / "config.json"
    assert json.loads(runtime_config.read_text(encoding="utf-8"))[
        "memory_space_id"
    ] == "shared-default"
    assert "__LEDGERMIND_CONFIG__" not in "".join(
        path.read_text(encoding="utf-8")
        for path in adapter._plugin_root(context).glob("*")
        if path.is_file()
    )
    if spec.target_id == "openclaw":
        agent_config = home / "openclaw.json"
        payload = json.loads(agent_config.read_text(encoding="utf-8"))
        assert payload["plugins"]["allow"] == ["ledgermind-memory"]
        assert payload["plugins"]["entries"]["ledgermind-memory"]["hooks"] == {
            "allowConversationAccess": True,
            "allowPromptInjection": True,
        }
        adapter.repair(context)
        payload = json.loads(agent_config.read_text(encoding="utf-8"))
        assert payload["plugins"]["allow"] == ["ledgermind-memory"]
        payload["user_setting"] = "keep"
        agent_config.write_text(json.dumps(payload), encoding="utf-8")
        adapter.uninstall(context)
        restored = json.loads(agent_config.read_text(encoding="utf-8"))
        assert restored["user_setting"] == "keep"
        assert "ledgermind-memory" not in restored["plugins"]["entries"]
        assert "ledgermind-memory" not in restored["plugins"]["allow"]


def test_registry_exposes_all_supported_clients() -> None:
    assert set(target_ids()) == {
        "hermes",
        "codex",
        "claude-code",
        "cursor",
        "opencode",
        "openclaw",
    }


@pytest.mark.parametrize("spec", SPECS, ids=lambda spec: spec.target_id)
def test_command_adapters_use_the_shared_memory_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spec
) -> None:
    home = tmp_path / spec.target_id
    home.mkdir()
    monkeypatch.setenv(spec.env_home, str(home))
    adapter = LifecycleTargetAdapter(spec)
    context = AdapterContext(
        config=_config().model_copy(update={"memory_mode": "shared"}),
        paths=InstallerPaths(home_override=tmp_path / "install"),
        discovery=adapter.discover(),
    )

    adapter.install(context)

    runtime_config = context.paths.integrations_dir / spec.target_id / "config.json"
    assert json.loads(runtime_config.read_text(encoding="utf-8"))[
        "memory_space_id"
    ] == "shared-default"


def test_cursor_discovery_accepts_official_cursor_agent_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cursor_spec = next(spec for spec in SPECS if spec.target_id == "cursor")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    cursor_agent = binary_dir / "cursor-agent"
    cursor_agent.write_text("#!/bin/sh\n", encoding="utf-8")
    cursor_agent.chmod(0o700)
    monkeypatch.setenv("PATH", str(binary_dir))
    monkeypatch.setenv("CURSOR_HOME", str(tmp_path / "missing-home"))

    discovery = LifecycleTargetAdapter(cursor_spec).discover()

    assert discovery.detected is True
