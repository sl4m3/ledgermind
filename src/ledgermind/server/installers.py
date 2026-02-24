import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class BaseInstaller:
    def __init__(self, client_name: str):
        self.client_name = client_name
        self.home_dir = str(Path.home())

    def install(self, project_path: str):
        raise NotImplementedError

    def uninstall(self):
        raise NotImplementedError


class ClaudeInstaller(BaseInstaller):
    def __init__(self):
        super().__init__("claude")
        self.claude_dir = os.path.join(self.home_dir, ".claude")
        self.hooks_dir = os.path.join(self.claude_dir, "hooks")
        self.settings_file = os.path.join(self.claude_dir, "settings.json")

    def install(self, project_path: str):
        os.makedirs(self.hooks_dir, exist_ok=True)
        
        # 1. Create UserPromptSubmit / BeforeModel script
        before_script_path = os.path.join(self.hooks_dir, "ledgermind_before_prompt.sh")
        with open(before_script_path, "w") as f:
            f.write(f"""#!/bin/bash
# LedgerMind BeforeModel Hook
# Injects context into the prompt
PROMPT=$(cat)
ledgermind-mcp bridge-context --path "{project_path}" --prompt "$PROMPT" --cli "claude"
""")
        os.chmod(before_script_path, 0o700)

        # 2. Create PostToolUse / AfterModel script
        after_script_path = os.path.join(self.hooks_dir, "ledgermind_after_interaction.sh")
        with open(after_script_path, "w") as f:
            f.write(f"""#!/bin/bash
# LedgerMind AfterModel Hook
# Records the interaction (fire and forget)
RESPONSE=$(cat)
ledgermind-mcp bridge-record --path "{project_path}" --prompt "Automated tool execution" --response "$RESPONSE" --cli "claude" &
""")
        os.chmod(after_script_path, 0o700)

        # 3. Update settings.json
        settings = {}
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    settings = json.load(f)
            except json.JSONDecodeError:
                settings = {}

        if "hooks" not in settings:
            settings["hooks"] = {}

        settings["hooks"]["UserPromptSubmit"] = before_script_path
        settings["hooks"]["PostToolUse"] = after_script_path
        settings["hooks"]["AfterModel"] = after_script_path

        with open(self.settings_file, "w") as f:
            json.dump(settings, f, indent=2)

        print(f"✓ Installed Claude hooks successfully.")


class CursorInstaller(BaseInstaller):
    def __init__(self):
        super().__init__("cursor")
        self.cursor_dir = os.path.join(self.home_dir, ".cursor")
        self.hooks_dir = os.path.join(self.cursor_dir, "hooks")
        self.hooks_file = os.path.join(self.cursor_dir, "hooks.json")

    def install(self, project_path: str):
        os.makedirs(self.hooks_dir, exist_ok=True)
        
        before_script_path = os.path.join(self.hooks_dir, "ledgermind_before.sh")
        with open(before_script_path, "w") as f:
            f.write(f"""#!/bin/bash
# Cursor BeforeSubmitPrompt Hook
PROMPT=$1
ledgermind-mcp bridge-context --path "{project_path}" --prompt "$PROMPT" --cli "cursor"
""")
        os.chmod(before_script_path, 0o700)

        after_script_path = os.path.join(self.hooks_dir, "ledgermind_after.sh")
        with open(after_script_path, "w") as f:
            f.write(f"""#!/bin/bash
# Cursor AfterAgentResponse Hook
RESPONSE=$1
ledgermind-mcp bridge-record --path "{project_path}" --prompt "Agent interaction" --response "$RESPONSE" --cli "cursor" &
""")
        os.chmod(after_script_path, 0o700)

        hooks_config = {}
        if os.path.exists(self.hooks_file):
            try:
                with open(self.hooks_file, "r") as f:
                    hooks_config = json.load(f)
            except json.JSONDecodeError:
                hooks_config = {}

        hooks_config["beforeSubmitPrompt"] = before_script_path
        hooks_config["afterAgentResponse"] = after_script_path
        hooks_config["afterAgentThought"] = after_script_path

        with open(self.hooks_file, "w") as f:
            json.dump(hooks_config, f, indent=2)

        print(f"✓ Installed Cursor hooks successfully.")


class GeminiInstaller(BaseInstaller):
    def __init__(self):
        super().__init__("gemini")
        self.gemini_dir = os.path.join(self.home_dir, ".gemini")
        self.hooks_dir = os.path.join(self.gemini_dir, "hooks")

    def install(self, project_path: str):
        os.makedirs(self.hooks_dir, exist_ok=True)
        # For Gemini CLI, we create a Python hook that the CLI can import or call
        hook_file = os.path.join(self.hooks_dir, "ledgermind_hook.py")
        with open(hook_file, "w") as f:
            f.write(f"""
import os
import sys

# Add the project's src directory to sys.path if not already there
# This ensures we can import ledgermind even if not installed globally
project_src = os.path.join("{project_path}", "src")
if os.path.exists(project_src) and project_src not in sys.path:
    sys.path.insert(0, project_src)

try:
    from ledgermind.core.api.bridge import IntegrationBridge
    bridge = IntegrationBridge(memory_path="{project_path}", default_cli=["gemini"])
    
    def before_prompt(prompt):
        \"\"\"Injected before sending the prompt to the LLM.\"\"\"
        return bridge.get_context_for_prompt(prompt)

    def after_interaction(prompt, response, success=True, metadata=None):
        \"\"\"Injected after receiving the response from the LLM.\"\"\"
        bridge.record_interaction(prompt=prompt, response=response, success=success, metadata=metadata)
        
except ImportError:
    # Silent fail if ledgermind is not available to avoid breaking the CLI
    pass
""")
        print(f"✓ Installed Gemini CLI hooks successfully.")


def install_client(client_name: str, project_path: str):
    installers = {
        "claude": ClaudeInstaller,
        "cursor": CursorInstaller,
        "gemini": GeminiInstaller,
    }
    
    if client_name not in installers:
        print(f"Error: Unsupported client '{client_name}'. Supported: {list(installers.keys())}")
        return False
        
    installer = installers[client_name]()
    try:
        installer.install(os.path.abspath(project_path))
        return True
    except Exception as e:
        print(f"✗ Failed to install {client_name} hooks: {e}")
        return False
