"""LedgerMind installer for Hermes — sets up plugin + venv + server."""

import os
import json
import shutil
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

HERMES_HOME = Path.home() / ".hermes"
HERMES_PLUGINS_DIR = HERMES_HOME / "plugins"
HERMES_CONFIG = HERMES_HOME / "config.yaml"
LEDGERMIND_HOME = Path.home() / ".ledgermind"
VENV_DIR = LEDGERMIND_HOME / "venv"

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


def _get_hermes_python() -> str:
    """Get Python executable used by Hermes."""
    hermes_venv = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python3"
    if hermes_venv.exists():
        return str(hermes_venv)
    return sys.executable


def _create_venv() -> bool:
    """Create venv with same Python version as Hermes."""
    hermes_python = _get_hermes_python()

    # Get Python version from Hermes
    try:
        result = subprocess.run(
            [hermes_python, "--version"],
            capture_output=True, text=True, timeout=5
        )
        version = result.stdout.strip().replace("Python ", "")
        major, minor = version.split(".")[:2]
        python_cmd = f"python{major}.{minor}"
    except Exception:
        python_cmd = "python3"

    if VENV_DIR.exists():
        logger.info("Venv already exists: %s", VENV_DIR)
        return True

    try:
        logger.info("Creating venv with %s at %s", python_cmd, VENV_DIR)
        subprocess.run(
            [python_cmd, "-m", "venv", str(VENV_DIR)],
            check=True, timeout=30
        )
        return True
    except Exception as e:
        logger.error("Failed to create venv: %s", e)
        return False


def _install_ledgermind() -> bool:
    """Install ledgermind into venv."""
    pip = VENV_DIR / "bin" / "pip"
    if not pip.exists():
        pip = VENV_DIR / "Scripts" / "pip.exe"  # Windows

    try:
        logger.info("Installing ledgermind...")
        subprocess.run(
            [str(pip), "install", "ledgermind"],
            check=True, timeout=120
        )
        return True
    except Exception as e:
        logger.error("Failed to install ledgermind: %s", e)
        return False


def _download_model() -> bool:
    """Download embedding model Jina v5 small Q4_K_M."""
    import urllib.request
    import urllib.error

    model_url = "https://huggingface.co/jinaai/jina-embeddings-v5-text-small-text-matching-GGUF/resolve/main/v5-small-text-matching-Q4_K_M.gguf"
    model_dir = LEDGERMIND_HOME / "hermes" / "models"
    model_path = model_dir / "v5-small-text-matching-Q4_K_M.gguf"

    if model_path.exists():
        logger.info("Model already exists: %s", model_path)
        return True

    try:
        model_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading embedding model (~378 MB)...")

        req = urllib.request.Request(model_url)
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0

            with open(model_path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = (downloaded / total) * 100
                        print(f"\r  Downloading: {percent:.1f}%", end="", flush=True)

            print()  # New line after progress
            logger.info("Model downloaded: %s", model_path)
            return True
    except Exception as e:
        logger.error("Failed to download model: %s", e)
        # Clean up partial download
        if model_path.exists():
            model_path.unlink()
        return False


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
"""


def get_state_db_stats() -> dict:
    """Get session/message counts from Hermes state.db."""
    state_db = HERMES_HOME / "state.db"
    if not state_db.exists():
        return {"exists": False}
    try:
        import sqlite3
        conn = sqlite3.connect(str(state_db))
        sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        conn.close()
        return {"exists": True, "sessions": sessions, "messages": messages}
    except Exception:
        return {"exists": False}


def install_hermes(
    mode: str = "agent",
    enrichment: str = "openrouter",
    api_key: str = None,
    base_url: str = None,
    language: str = "english",
    import_limit: int = None,
    gpu_layers: int = 0,
) -> dict:
    """Install LedgerMind plugin for Hermes.

    import_limit: REQUIRED. Number of recent events to import from state.db.
        Use 0 to skip import, -1 for all, or a positive number for last N events.
        Non-interactive mode MUST provide this — caller should ask the user first.
    gpu_layers: Number of GPU layers for GGUF model. 0 = CPU only, 99 = all layers on GPU.
    """
    result = {"success": False, "messages": [], "errors": []}

    # Validate import_limit
    if import_limit is None:
        stats = get_state_db_stats()
        if stats.get("exists") and stats.get("messages", 0) > 0:
            result["errors"].append(
                f"import_limit is required. state.db has {stats['messages']} messages. "
                f"Ask the user how many recent events to import (0=skip, -1=all, N=last N)."
            )
            return result
        import_limit = 0

    if not _detect_hermes():
        result["errors"].append(
            "Hermes not found. Install it first:\n"
            "  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
        )
        return result

    result["messages"].append(f"Hermes found: {HERMES_HOME}")

    # Step 1: Create venv
    if not _create_venv():
        result["errors"].append("Failed to create venv")
        return result
    result["messages"].append(f"Venv ready: {VENV_DIR}")

    # Step 2: Install ledgermind
    if not _install_ledgermind():
        result["errors"].append("Failed to install ledgermind in venv")
        return result
    result["messages"].append("LedgerMind installed in venv")

    # Step 3: Download embedding model
    if not _download_model():
        result["errors"].append("Failed to download embedding model")
        return result
    result["messages"].append("Embedding model downloaded")

    # Step 4: Copy plugin
    plugin_dir = HERMES_PLUGINS_DIR / "ledgermind"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    source_init = Path(__file__).parent.parent.parent.parent / "ledgermind_plugin" / "__init__.py"
    target_init = plugin_dir / "__init__.py"
    if source_init.exists():
        shutil.copy2(source_init, target_init)
    else:
        result["errors"].append(f"Plugin source not found: {source_init}")
        return result
    result["messages"].append(f"Plugin code: {target_init}")

    plugin_yaml = plugin_dir / "plugin.yaml"
    plugin_yaml.write_text(PLUGIN_YAML, encoding="utf-8")
    result["messages"].append(f"Plugin manifest: {plugin_yaml}")

    # Step 5: Write config
    defaults = ENRICHMENT_DEFAULTS.get(enrichment, ENRICHMENT_DEFAULTS["openrouter"])
    if base_url is None:
        base_url = defaults["base_url"]
    model = defaults["model"]

    plugin_config = {
        "provider": enrichment,
        "model": model,
        "base_url": base_url,
        "venv_python": str(VENV_DIR / "bin" / "python3"),
    }

    # API key in .env
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
        "import_limit": import_limit,
        "gpu_layers": gpu_layers,
        "initial_import_done": {},
    }
    lm_config_path = LEDGERMIND_HOME / "hermes" / "config.json"
    lm_config_path.parent.mkdir(parents=True, exist_ok=True)
    lm_config_path.write_text(json.dumps(lm_config, indent=2), encoding="utf-8")
    result["messages"].append(f"LedgerMind config: {lm_config_path}")

    # Step 6: Enable plugin
    if _enable_plugin_in_config("ledgermind"):
        result["messages"].append("Plugin enabled in Hermes config")
    else:
        result["errors"].append("Failed to enable plugin in Hermes config")
        return result

    result["success"] = True
    return result


def install_interactive() -> dict:
    """Interactive installation — asks questions via prompt."""
    stats = get_state_db_stats()
    total_messages = stats.get("messages", 0) if stats.get("exists") else 0

    try:
        import questionary
    except ImportError:
        print("LedgerMind Installer for Hermes\n")

        mode = input("Mode (agent/core) [agent]: ").strip() or "agent"
        enrichment = input("Enrichment provider (openrouter/nvidia/aistudio/custom) [openrouter]: ").strip() or "openrouter"
        api_key = input(f"API key for {enrichment}: ").strip()
        base_url = input("Base URL (empty for default): ").strip() or None
        language = input("Language (english/russian) [english]: ").strip() or "english"
        gpu_input = input("Embedding model device (cpu/gpu) [cpu]: ").strip().lower() or "cpu"
        gpu_layers = 99 if gpu_input == "gpu" else 0

        if total_messages > 0:
            print(f"\nstate.db: {total_messages} messages in {stats.get('sessions', 0)} sessions")
            limit_input = input("Import events (0=skip, -1=all, N=last N) [1000]: ").strip() or "1000"
            import_limit = int(limit_input)
        else:
            import_limit = 0
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

        gpu_choice = questionary.select(
            "Embedding model device:",
            choices=["CPU (slower, works everywhere)", "GPU via CUDA (faster, requires CUDA)"],
            default="CPU (slower, works everywhere)",
        ).ask()
        if gpu_choice is None:
            return {"success": False, "errors": ["Installation cancelled"]}
        gpu_layers = 99 if "GPU" in gpu_choice else 0

        if total_messages > 0:
            import_limit = questionary.select(
                f"Import events from state.db ({total_messages} messages in {stats.get('sessions', 0)} sessions):",
                choices=[
                    f"Last 1,000 (recommended)",
                    f"Last 5,000",
                    f"Last 10,000",
                    f"All {total_messages}",
                    "Skip import",
                ],
                default=f"Last 1,000 (recommended)",
            ).ask()
            if import_limit is None:
                return {"success": False, "errors": ["Installation cancelled"]}

            limit_map = {
                "Last 1,000 (recommended)": 1000,
                "Last 5,000": 5000,
                "Last 10,000": 10000,
                f"All {total_messages}": -1,
                "Skip import": 0,
            }
            import_limit = limit_map.get(import_limit, 1000)
        else:
            import_limit = 0

    return install_hermes(
        mode=mode,
        enrichment=enrichment,
        api_key=api_key or None,
        base_url=base_url or None,
        language=language,
        import_limit=import_limit,
        gpu_layers=gpu_layers,
    )
