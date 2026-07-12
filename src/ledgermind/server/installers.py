import os
import json
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

HERMES_HOME = Path.home() / ".hermes"
HERMES_PLUGINS_DIR = HERMES_HOME / "plugins"
HERMES_CONFIG = HERMES_HOME / "config.yaml"
LEDGERMIND_HOME = Path.home() / ".ledgermind" / "hermes"

ENRICHMENT_DEFAULTS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "deepseek-ai/deepseek-v4-flash",
    },
    "aistudio": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemma-4-31b-it",
    },
    "custom": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama-3-8b",
    },
}


def _detect_hermes() -> bool:
    """Check if Hermes is installed."""
    return HERMES_HOME.exists() and HERMES_CONFIG.exists()


def _find_ledgermind_path() -> str | None:
    """Find where ledgermind is installed and return its parent dir for sys.path."""
    import importlib.util
    spec = importlib.util.find_spec("ledgermind")
    if spec and spec.origin:
        # spec.origin = .../ledgermind/__init__.py
        # We need the parent of the package dir
        return str(Path(spec.origin).parent.parent)
    return None


def _enable_plugin_in_config(plugin_name: str) -> bool:
    """Enable plugin in Hermes config.yaml."""
    if not HERMES_CONFIG.exists():
        logger.warning("Hermes config not found at %s", HERMES_CONFIG)
        return False

    try:
        import yaml
        with open(HERMES_CONFIG, "r") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("Failed to read Hermes config: %s", e)
        return False

    plugins = config.setdefault("plugins", {})
    enabled = plugins.setdefault("enabled", [])
    if plugin_name not in enabled:
        enabled.append(plugin_name)

    with open(HERMES_CONFIG, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    return True


PLUGIN_YAML = """\
name: ledgermind
version: 1.0.0
description: Autonomous memory management for AI agents
author: Stanislav Zotov
provides_hooks:
  - pre_llm_call
  - post_llm_call
  - on_session_start
  - on_session_end
"""


def install_hermes(
    mode: str = "agent",
    enrichment: str = "openrouter",
    api_key: str = None,
    base_url: str = None,
    language: str = "english",
) -> dict:
    """Install LedgerMind plugin for Hermes."""
    result = {"success": False, "messages": [], "errors": []}

    if not _detect_hermes():
        result["errors"].append(
            "Hermes not found. Install it first:\n"
            "  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
        )
        return result

    result["messages"].append(f"Hermes found: {HERMES_HOME}")

    defaults = ENRICHMENT_DEFAULTS.get(enrichment, ENRICHMENT_DEFAULTS["openrouter"])
    if base_url is None:
        base_url = defaults["base_url"]
    model = defaults["model"]

    plugin_dir = HERMES_PLUGINS_DIR / "ledgermind"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    plugin_yaml = plugin_dir / "plugin.yaml"
    plugin_yaml.write_text(PLUGIN_YAML, encoding="utf-8")
    result["messages"].append(f"Plugin manifest: {plugin_yaml}")

    source_init = Path(__file__).parent.parent.parent.parent / "ledgermind_plugin" / "__init__.py"
    target_init = plugin_dir / "__init__.py"
    if source_init.exists():
        # Find ledgermind's install path and inject into plugin
        ledgermind_parent = _find_ledgermind_path()
        if ledgermind_parent:
            content = source_init.read_text(encoding="utf-8")
            sys_path_line = f'import sys; sys.path.insert(0, "{ledgermind_parent}")\n'
            if "sys.path" not in content:
                content = sys_path_line + content
            target_init.write_text(content, encoding="utf-8")
            result["messages"].append(f"Injected ledgermind path: {ledgermind_parent}")
        else:
            shutil.copy2(source_init, target_init)
            result["messages"].append("Warning: ledgermind path not found, plugin may not find imports")
    else:
        result["errors"].append(f"Plugin source not found: {source_init}")
        return result
    result["messages"].append(f"Plugin code: {target_init}")

    plugin_config = {
        "provider": enrichment,
        "model": model,
        "base_url": base_url,
    }
    config_path = plugin_dir / "config.json"
    config_path.write_text(json.dumps(plugin_config, indent=2), encoding="utf-8")
    result["messages"].append(f"Plugin config: {config_path}")

    env_path = plugin_dir / ".env"
    env_content = f"LEDGERMIND_API_KEY={api_key or ''}\n"
    env_path.write_text(env_content, encoding="utf-8")
    os.chmod(env_path, 0o600)
    result["messages"].append(f"API key: {env_path}")

    LEDGERMIND_HOME.mkdir(parents=True, exist_ok=True)

    lm_config = {
        "default_mode": mode,
        "language": language,
        "enrichment": plugin_config,
        "initial_import_done": {},
    }
    lm_config_path = LEDGERMIND_HOME / "config.json"
    lm_config_path.write_text(json.dumps(lm_config, indent=2), encoding="utf-8")
    result["messages"].append(f"LedgerMind config: {lm_config_path}")

    if _enable_plugin_in_config("ledgermind"):
        result["messages"].append("Plugin enabled in Hermes config")
    else:
        result["errors"].append("Failed to enable plugin in Hermes config")
        return result

    result["success"] = True
    return result


def install_interactive() -> dict:
    """Interactive installation — asks questions via prompt."""
    try:
        import questionary
    except ImportError:
        print("LedgerMind Installer for Hermes\n")

        mode = input("Mode (agent/core) [agent]: ").strip() or "agent"
        enrichment = input("Enrichment provider (openrouter/nvidia/aistudio/custom) [openrouter]: ").strip() or "openrouter"
        api_key = input(f"API key for {enrichment}: ").strip()
        base_url = input("Base URL (empty for default): ").strip() or None
        language = input("Language (english/russian) [english]: ").strip() or "english"
    else:
        print("\nLedgerMind Installer for Hermes\n")

        mode = questionary.select(
            "Mode:",
            choices=["agent", "core"],
            default="agent",
        ).ask()
        if mode is None:
            return {"success": False, "errors": ["Installation cancelled"]}

        enrichment = questionary.select(
            "Enrichment provider:",
            choices=["openrouter", "nvidia", "aistudio", "custom"],
            default="openrouter",
        ).ask()
        if enrichment is None:
            return {"success": False, "errors": ["Installation cancelled"]}

        api_key = questionary.text(
            f"API key for {enrichment}:",
            default="",
        ).ask()
        if api_key is None:
            return {"success": False, "errors": ["Installation cancelled"]}

        base_url = questionary.text(
            "Base URL (empty for default):",
            default="",
        ).ask()
        if base_url is None:
            return {"success": False, "errors": ["Installation cancelled"]}

        language = questionary.select(
            "Language:",
            choices=["english", "russian"],
            default="english",
        ).ask()
        if language is None:
            return {"success": False, "errors": ["Installation cancelled"]}

    return install_hermes(
        mode=mode,
        enrichment=enrichment,
        api_key=api_key or None,
        base_url=base_url or None,
        language=language,
    )
