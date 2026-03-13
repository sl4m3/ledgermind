import os
import shutil
import subprocess
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("ledgermind.utils.gemini_config")

class GeminiConfigManager:
    """
    Manages Gemini CLI binary discovery and configuration file setup.
    Supports global (~/.gemini/settings.json) and project-level (.gemini/settings.json) modes.
    """
    
    @staticmethod
    def discover_binary() -> Optional[str]:
        """Attempts to find the 'gemini' CLI binary in PATH."""
        return shutil.which("gemini")

    @staticmethod
    def get_config_path(mode: str = "global", 
                        global_path: str = "~/.gemini/settings.json",
                        project_path: str = None) -> str:
        """Returns the absolute path to the gemini config based on mode."""
        if mode == "project":
            # If project_path is a directory, append default filename
            p = project_path or "."
            if os.path.isdir(p):
                return os.path.abspath(os.path.join(p, ".gemini", "settings.json"))
            else:
                return os.path.abspath(p)
        else:
            return os.path.expanduser(global_path)

    @staticmethod
    def ensure_config_exists(path: str, default_settings: Optional[Dict[str, Any]] = None):
        """Creates the config file and its parent directories if they don't exist."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            settings = default_settings or {
                "model": "gemini-2.0-flash",
                "temperature": 0.3,
                "maxOutputTokens": 2048
            }
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, indent=2)
                logger.info(f"Created new Gemini config at {path}")
            except Exception as e:
                logger.error(f"Failed to create Gemini config at {path}: {e}")

    @staticmethod
    def get_environment(config_path: str) -> Dict[str, str]:
        """Returns environment variables required for Gemini CLI to use the specific config."""
        env = os.environ.copy()
        # Gemini CLI usually looks for config in specific places or via env vars
        # If the CLI supports a custom config path via env, set it here.
        # Based on typical patterns, we might set GEMINI_CONFIG_PATH or similar.
        env["GEMINI_CONFIG_PATH"] = config_path
        env["LEDGERMIND_BYPASS_HOOKS"] = "1"
        return env
