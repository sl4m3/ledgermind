import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseInstaller:
    """Base class for client installers."""

    def __init__(self, client_name: str):
        self.client_name = client_name
        self.home_dir = str(Path.home())

    def install(self, project_path: str, memory_path: str = None):
        raise NotImplementedError

    def uninstall(self):
        raise NotImplementedError

    def _create_hook_script(self, script_path: str, content: str):
        with open(script_path, "w") as f:
            f.write(content)
        os.chmod(script_path, 0o700)

    def _add_mcp_to_config(self, config_path: str, memory_path: str):
        """Helper: inject MCP server config into a settings.json file."""
        config_dir = os.path.dirname(config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)

        config = {"mcpServers": {}}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
            except json.JSONDecodeError:
                config = {"mcpServers": {}}
        else:
            config = {"mcpServers": {}}

        if "mcpServers" not in config:
            config["mcpServers"] = {}

        config["mcpServers"]["ledgermind"] = {
            "command": "ledgermind-mcp",
            "args": ["run", "--path", os.path.abspath(memory_path)],
            "disabled": False
        }

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
