import os
import json
import logging
import platform
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


class ClaudeInstaller(BaseInstaller):
    def __init__(self):
        super().__init__("claude")
        self.global_settings = os.path.join(self.home_dir, ".claude", "settings.json")

    def install(self, project_path: str, memory_path: str = None):
        project_path = os.path.abspath(project_path)
        # Determine memory path
        if memory_path is None:
            memory_path = os.path.join(os.path.dirname(project_path), ".ledgermind")
        # Hooks are now stored INSIDE the project
        project_hooks_dir = os.path.join(project_path, ".claude", "hooks")
        os.makedirs(project_hooks_dir, exist_ok=True)
        
        # 1. Create UserPromptSubmit script (Context injection & backup sync)
        before_script_path = os.path.join(project_hooks_dir, "ledgermind_before_prompt.sh")
        cli_entry = f"python3 -m ledgermind.server.cli"
        self._create_hook_script(before_script_path, f"""#!/bin/bash
# LedgerMind UserPromptSubmit Hook (Local to {project_path})
if [ "$LEDGERMIND_BYPASS_HOOKS" = "1" ]; then exit 0; fi
LOG_FILE="$HOME/.claude/ledgermind_hooks.log"
echo "[$(date)] UserPromptSubmit triggered" >> "$LOG_FILE"
export PYTHONPATH="{project_path}/src":$PYTHONPATH
cat | {cli_entry} bridge-context --path "{memory_path}" --prompt "-" --cli "claude" --stdin 2>> "$LOG_FILE"
""")

        # 2. Create Stop script (Real-time transcript sync)
        stop_script_path = os.path.join(project_hooks_dir, "ledgermind_stop.sh")
        self._create_hook_script(stop_script_path, f"""#!/bin/bash
# LedgerMind Stop Hook (Local to {project_path})
if [ "$LEDGERMIND_BYPASS_HOOKS" = "1" ]; then exit 0; fi
LOG_FILE="$HOME/.claude/ledgermind_hooks.log"
echo "[$(date)] Stop hook triggered" >> "$LOG_FILE"
export PYTHONPATH="{project_path}/src":$PYTHONPATH
cat | {cli_entry} bridge-sync --path "{memory_path}" --cli "claude" --stdin 2>> "$LOG_FILE"
""")

        # 3. Update global and local settings.json
        settings_paths = [
            self.global_settings,
            os.path.join(project_path, ".claude", "settings.json")
        ]

        for s_path in settings_paths:
            settings = {}
            if os.path.exists(s_path):
                try:
                    with open(s_path, "r") as f:
                        settings = json.load(f)
                except json.JSONDecodeError:
                    settings = {}

            if "hooks" not in settings:
                settings["hooks"] = {}

            # UserPromptSubmit: trigger on all prompts with absolute path
            settings["hooks"]["UserPromptSubmit"] = [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": os.path.abspath(before_script_path)
                        }
                    ]
                }
            ]
            
            # Stop: trigger when Claude finishes responding with absolute path
            settings["hooks"]["Stop"] = [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": os.path.abspath(stop_script_path)
                        }
                    ]
                }
            ]

            # Clean up legacy/redundant hooks
            for h in ["AfterModel", "PostToolUse", "PreToolUse"]:
                if h in settings["hooks"]:
                    del settings["hooks"][h]

            os.makedirs(os.path.dirname(s_path), exist_ok=True)
            with open(s_path, "w") as f:
                json.dump(settings, f, indent=2)
            
            print(f"✓ Configured Claude hooks in: {s_path}")

        print(f"✓ Installed Claude hooks locally in {project_hooks_dir}")

    def install_mcp_server(self, project_path: str, memory_path: str, client: str = "claude"):
        """Install MCP server configuration for Claude via claude mcp add."""
        try:
            import subprocess
            import shutil
            claude_path = shutil.which("claude")
            if not claude_path:
                raise FileNotFoundError("Claude CLI not found")
            # Try to add with client parameter
            result = subprocess.run(  # nosec B603
                [claude_path, "mcp", "add", "ledgermind", "ledgermind-mcp", "--", "--path", os.path.abspath(memory_path), "--client", client],
                capture_output=True, text=True, timeout=30
            )

            # If it fails because it already exists, remove it and try again to update the path
            if result.returncode != 0 and "already exists" in (result.stderr or result.stdout):
                subprocess.run([claude_path, "mcp", "remove", "ledgermind"], capture_output=True, timeout=10)  # nosec B603
                result = subprocess.run(  # nosec B603
                    [claude_path, "mcp", "add", "ledgermind", "ledgermind-mcp", "--", "--path", os.path.abspath(memory_path), "--client", client],
                    capture_output=True, text=True, timeout=30
                )

            if result.returncode == 0:
                print(f"✓ Added LedgerMind MCP server to Claude Desktop (client: {client})")
                return True
            else:
                print(f"! Failed to add MCP to Claude: {result.stderr.strip() if result.stderr else result.stdout.strip()}")
                return False
        except FileNotFoundError:
            print("! Claude CLI not found. Install it from https://claude.ai/download")
            return False
        except Exception as e:
            print(f"! Error adding MCP to Claude: {e}")
            return False


class CursorInstaller(BaseInstaller):
    def __init__(self):
        super().__init__("cursor")
        self.global_hooks_file = os.path.join(self.home_dir, ".cursor", "hooks.json")

    def install(self, project_path: str, memory_path: str = None):
        project_path = os.path.abspath(project_path)
        if memory_path is None:
            memory_path = os.path.join(os.path.dirname(project_path), ".ledgermind")
        project_hooks_dir = os.path.join(project_path, ".ledgermind", "hooks")
        os.makedirs(project_hooks_dir, exist_ok=True)
        
        before_script_path = os.path.join(project_hooks_dir, "ledgermind_before.sh")
        self._create_hook_script(before_script_path, f"""#!/bin/bash
# Cursor BeforeSubmitPrompt Hook (Local to {project_path})
if [ "$LEDGERMIND_BYPASS_HOOKS" = "1" ]; then exit 0; fi
PROMPT=$1
ledgermind-mcp bridge-context --path "{memory_path}" --prompt "$PROMPT" --cli "cursor"
""")

        after_script_path = os.path.join(project_hooks_dir, "ledgermind_after.sh")
        self._create_hook_script(after_script_path, f"""#!/bin/bash
# Cursor AfterAgentResponse Hook (Local to {project_path})
if [ "$LEDGERMIND_BYPASS_HOOKS" = "1" ]; then exit 0; fi
RESPONSE=$1
ledgermind-mcp bridge-record --path "{memory_path}" --prompt "Agent interaction" --response "$RESPONSE" --cli "cursor" &
""")

        hooks_config = {}
        if os.path.exists(self.global_hooks_file):
            try:
                with open(self.global_hooks_file, "r") as f:
                    hooks_config = json.load(f)
            except json.JSONDecodeError:
                hooks_config = {}

        hooks_config["beforeSubmitPrompt"] = before_script_path
        hooks_config["afterAgentResponse"] = after_script_path
        hooks_config["afterAgentThought"] = after_script_path

        os.makedirs(os.path.dirname(self.global_hooks_file), exist_ok=True)
        with open(self.global_hooks_file, "w") as f:
            json.dump(hooks_config, f, indent=2)

        print(f"✓ Installed Cursor hooks locally in {project_hooks_dir}")


class GeminiInstaller(BaseInstaller):
    def __init__(self, config_mode: str = "global"):
        super().__init__("gemini")
        self.config_mode = config_mode

    def install(self, project_path: str, memory_path: str = None):
        project_path = os.path.abspath(project_path)
        if memory_path is None:
            memory_path = os.path.join(os.path.dirname(project_path), ".ledgermind")
        
        # Store hooks in .gemini/hooks inside the project (as in ledgermind repo)
        project_hooks_dir = os.path.join(project_path, ".gemini", "hooks")
        os.makedirs(project_hooks_dir, exist_ok=True)

        hook_file = os.path.join(project_hooks_dir, "ledgermind_hook.py")
        
        # 1. Create the hook script
        with open(hook_file, "w") as f:
            f.write(f"""import os
import sys

if os.environ.get("LEDGERMIND_BYPASS_HOOKS") == "1":
    sys.exit(0)

import datetime
import json

LOG_FILE = os.path.expanduser('~/.gemini/hooks/ledgermind_debug.log')
PROJECT_PATH = '{project_path}'
MEMORY_PATH = '{memory_path}'

def log_debug(msg):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(f'{{datetime.datetime.now()}} - {{msg}}\\n')
    except:
        pass

def main():
    log_debug(f'--- Hook Execution Start ---')
    log_debug(f'Args: {{sys.argv}}')

    stdin_json = {{}}
    prompt = ''
    if not sys.stdin.isatty():
        try:
            raw_input = sys.stdin.read()
            if raw_input:
                stdin_json = json.loads(raw_input)
                prompt = stdin_json.get('prompt', '')
            log_debug(f'Captured input (prompt length: {{len(prompt)}})')
        except Exception as e:
            log_debug(f'Error parsing input: {{str(e)}}')

    project_src = os.path.join(PROJECT_PATH, 'src')
    if os.path.exists(project_src) and project_src not in sys.path:
        sys.path.insert(0, project_src)

    try:
        from ledgermind.core.api.bridge import IntegrationBridge
        bridge = IntegrationBridge(memory_path=MEMORY_PATH)

        action = sys.argv[1] if len(sys.argv) > 1 else 'unknown'

        if action == 'before':
            log_debug('Processing BeforeAgent')
            if prompt:
                # Record prompt to episodic memory
                bridge.memory.process_event(source='user', kind='prompt', content=prompt)
                log_debug('Prompt recorded to episodic.db')

                # Fetch context
                context = bridge.get_context_for_prompt(prompt)
                if context:
                    # Return formatted JSON for context injection
                    output = {{
                        "hookSpecificOutput": {{
                            "additionalContext": context
                        }}
                    }}
                    sys.stdout.write(json.dumps(output) + '\\n')
                    log_debug('Context injected via JSON output')
                else:
                    # Return empty JSON if no context found
                    sys.stdout.write(json.dumps({{}}) + '\\n')
            else:
                sys.stdout.write(json.dumps({{}}) + '\\n')

        elif action == 'after':
            log_debug('Processing AfterAgent')
            if stdin_json:
                try:
                    # Gemini CLI passes the transcript path in the JSON input
                    transcript_path = stdin_json.get("transcript_path")
                    if transcript_path and os.path.exists(transcript_path):
                        with open(transcript_path, 'r', encoding='utf-8') as f:
                            transcript = json.load(f)

                        turns = transcript.get("messages", transcript.get("turns", []))
                        last_user_idx = -1
                        for i in range(len(turns) - 1, -1, -1):
                            if turns[i].get("type") == "user" or turns[i].get("role") == "user":
                                last_user_idx = i
                                break

                        agent_turns = turns[last_user_idx + 1:] if last_user_idx != -1 else []
                        if not agent_turns and turns:
                            agent_turns = [turns[-1]]

                        events_recorded = 0
                        for t in agent_turns:
                            if t.get("type") in ["gemini", "agent", "assistant"] or t.get("role") in ["assistant", "agent", "gemini"]:
                                text_content = t.get("content", "").strip()
                                if text_content:
                                    bridge.memory.process_event(source='agent', kind='result', content=text_content)
                                    events_recorded += 1

                                tool_calls = t.get("toolCalls", []) + t.get("tool_calls", [])
                                for tc in tool_calls:
                                    tool_name = tc.get("name", "unknown")
                                    status = tc.get("status", "unknown")
                                    args_str = json.dumps(tc.get("args", {{}}), ensure_ascii=False)

                                    result_str = tc.get("resultDisplay", "")
                                    if not result_str and tc.get("result"):
                                        result_str = json.dumps(tc.get("result"), ensure_ascii=False)

                                    tool_event_content = f"Tool: {{tool_name}}\\nStatus: {{status}}\\nArgs: {{args_str}}\\nResult:\\n{{result_str}}"
                                    bridge.memory.process_event(source='agent', kind='call', content=tool_event_content)
                                    events_recorded += 1

                        log_debug(f'Recorded {{events_recorded}} events from transcript')
                    else:
                        # Fallback to recording the raw response if no transcript
                        raw_response = stdin_json.get("response", "")
                        if raw_response:
                            bridge.memory.process_event(source='agent', kind='result', content=raw_response)
                            log_debug('Raw response recorded to episodic.db')

                except Exception as e:
                    log_debug(f'Error recording after interaction: {{e}}')

    except Exception as e:
        log_debug(f'Error in main: {{str(e)}}')

if __name__ == '__main__':
    main()
""")

        # 2. Update settings.json with hooks
        try:
            from ledgermind.core.utils.gemini_config import GeminiConfigManager
            if self.config_mode == "global":
                settings_path = GeminiConfigManager.get_config_path(mode="global")
            else:
                settings_path = GeminiConfigManager.get_config_path(mode="project", project_path=project_path)

            os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            
            config = {}
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, "r") as f:
                        config = json.load(f)
                except json.JSONDecodeError:
                    config = {}

            # Ensure hooksConfig exists
            if "hooksConfig" not in config:
                config["hooksConfig"] = {
                    "enabled": True,
                    "notifications": True,
                    "disabled": []
                }

            if "hooks" not in config:
                config["hooks"] = {}

            # Use relative path for hook script if it's a project config, otherwise absolute
            if self.config_mode == "project":
                hook_rel_path = ".gemini/hooks/ledgermind_hook.py"
            else:
                hook_rel_path = hook_file

            # Set BeforeAgent hook
            config["hooks"]["BeforeAgent"] = [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "name": "ledgermind-context",
                            "type": "command",
                            "command": f"python3 {hook_rel_path} before"
                        }
                    ]
                }
            ]

            # Set AfterAgent hook
            config["hooks"]["AfterAgent"] = [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "name": "ledgermind-record",
                            "type": "command",
                            "command": f"python3 {hook_rel_path} after"
                        }
                    ]
                }
            ]

            with open(settings_path, "w") as f:
                json.dump(config, f, indent=2)
            
            print(f"✓ Configured Gemini CLI hooks in: {settings_path}")
        except Exception as e:
            print(f"! Failed to configure Gemini CLI hooks in settings.json: {e}")

        print(f"✓ Installed Gemini CLI hooks successfully.")

    def install_mcp_server(self, project_path: str, memory_path: str, client: str = "gemini"):
        """Install MCP server configuration for Gemini."""
        try:
            from ledgermind.core.utils.gemini_config import GeminiConfigManager
            # Determine settings path based on self.config_mode
            if self.config_mode == "global":
                settings_path = GeminiConfigManager.get_config_path(mode="global", project_path=None)
            else:
                settings_path = GeminiConfigManager.get_config_path(mode="project", project_path=project_path)

            # Ensure directory exists
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)

            # Load existing or create new config
            config = {}
            if os.path.exists(settings_path):
                try:
                    with open(settings_path, "r") as f:
                        config = json.load(f)
                except json.JSONDecodeError:
                    config = {}

            if "mcpServers" not in config:
                config["mcpServers"] = {}

            # Add LedgerMind MCP server with client parameter
            config["mcpServers"]["ledgermind"] = {
                "command": "ledgermind-mcp",
                "args": ["run", "--path", os.path.abspath(memory_path), "--client", client]
            }

            with open(settings_path, "w") as f:
                json.dump(config, f, indent=2)

            print(f"✓ Added LedgerMind MCP server to Gemini settings ({self.config_mode}): {settings_path} (client: {client})")
            return True
        except Exception as e:
            print(f"! Failed to add MCP to Gemini settings: {e}")
            return False
            return False


class VSCodeInstaller(BaseInstaller):
    def __init__(self):
        super().__init__("vscode")
        if platform.system() == "Darwin": # macOS
            self.global_storage = os.path.expanduser("~/Library/Application Support/Code/User/globalStorage")
            self.extensions_dir = os.path.expanduser("~/.vscode/extensions")
        elif platform.system() == "Windows":
            self.global_storage = os.path.join(os.environ.get("APPDATA", ""), "Code", "User", "globalStorage")
            self.extensions_dir = os.path.join(os.environ.get("USERPROFILE", ""), ".vscode", "extensions")
        else: # Linux / Termux
            self.global_storage = os.path.expanduser("~/.config/Code/User/globalStorage")
            self.extensions_dir = os.path.expanduser("~/.vscode/extensions")

    def install(self, project_path: str, memory_path: str = None):
        project_path = os.path.abspath(project_path)
        if memory_path is None:
            memory_path = os.path.join(os.path.dirname(project_path), ".ledgermind")
        
        # 1. Физическая установка расширения LedgerMind
        self._install_extension_files(project_path)

        # 2. Roo Code (Cline) - settings path
        roo_path = os.path.join(self.global_storage, "saoudrizwan.claude-dev", "settings", "cline_mcp_settings.json")
        self._inject_mcp_config(roo_path, memory_path, "Roo Code (Cline)")

        # 3. Hardcore Zero-Touch: Добавляем системную инструкцию для автоматического чтения контекста
        # Путь к кастомным инструкциям Roo Code
        roo_instructions_path = os.path.join(self.global_storage, "saoudrizwan.claude-dev", "settings", "custom_instructions.json")
        self._inject_custom_instructions(roo_instructions_path)

        # 4. Continue.dev
        continue_config = os.path.expanduser("~/.continue/config.json")
        if os.path.exists(continue_config):
            print(f"! Continue.dev detected. Manual integration recommended in {continue_config}")

        print(f"✓ VS Code environment prepared for Hardcore Zero-Touch.")

    def _install_extension_files(self, project_path: str):
        import shutil
        import subprocess

        ext_src = os.path.join(project_path, "src", "ledgermind", "vscode")
        ext_dest = os.path.join(self.extensions_dir, "ledgermind.ledgermind-vscode")

        if not os.path.exists(ext_src):
            print(f"✗ Extension source not found at {ext_src}")
            return

        print(f"  → Installing LedgerMind VS Code extension to {ext_dest}...")
        
        # 1. Подготовка папки
        if os.path.exists(ext_dest):
            shutil.rmtree(ext_dest)
        os.makedirs(ext_dest, exist_ok=True)

        # 2. Попытка сборки (нужен npm и tsc)
        try:
            print("  → Compiling extension (npm install & tsc)...")
            npm_path = shutil.which("npm")
            if npm_path:
                subprocess.run([npm_path, "install"], cwd=ext_src, check=True, capture_output=True) # nosec B603 B607
                subprocess.run([npm_path, "run", "compile"], cwd=ext_src, check=True, capture_output=True) # nosec B603 B607
            else:
                print("! npm not found in PATH. Skipping compilation.")
        except Exception as e:
            print(f"! Compilation failed: {e}. You may need to run 'npm install && npm run compile' in {ext_src} manually.")

        # 3. Копирование файлов
        try:
            shutil.copy(os.path.join(ext_src, "package.json"), ext_dest)
            dist_path = os.path.join(ext_src, "dist")
            if os.path.exists(dist_path):
                shutil.copytree(dist_path, os.path.join(ext_dest, "dist"))
            else:
                # Если dist нет, копируем src (для разработки)
                shutil.copytree(os.path.join(ext_src, "src"), os.path.join(ext_dest, "src"))
            print(f"  → Extension files copied successfully.")
        except Exception as e:
            print(f"✗ Failed to copy extension files: {e}")

    def _inject_custom_instructions(self, path: str):
        instructions = "Always check for the existence of 'ledgermind_context.md' in the project root. If it exists, read it at the beginning of every task to synchronize with the autonomous memory and previous decisions."
        
        data = {}
        if os.path.exists(path):
            try:
                with open(path, "r") as f: data = json.load(f)
            except Exception: 
                data = {}

        # Добавляем или обновляем инструкцию
        if "global" not in data: data["global"] = ""
        if instructions not in data["global"]:
            data["global"] = (data["global"] + "\n\n" + instructions).strip()
            
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  → Injected Hardcore Memory Policy into Custom Instructions.")

    def _inject_mcp_config(self, config_path: str, memory_path: str, ext_name: str):
        config_dir = os.path.dirname(config_path)
        if not os.path.exists(config_dir):
            return

        config = {"mcpServers": {}}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
            except json.JSONDecodeError:
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
        print(f"  → Injected LedgerMind MCP into {ext_name} settings.")


def install_client(client_name: str, project_path: str, memory_path: str = None, **kwargs):
    installers = {
        "claude": lambda: ClaudeInstaller(),
        "cursor": lambda: CursorInstaller(),
        "gemini": lambda: GeminiInstaller(config_mode=kwargs.get('gemini_config_mode', 'global')),
        "vscode": lambda: VSCodeInstaller(),
    }

    if client_name not in installers:
        print(f"Error: Unsupported client '{client_name}'. Supported: {list(installers.keys())}")
        return False

    installer = installers[client_name]()
    try:
        installer.install(os.path.abspath(project_path), memory_path=memory_path)
        return True
    except Exception as e:
        print(f"✗ Failed to install {client_name} hooks: {e}")
        return False
