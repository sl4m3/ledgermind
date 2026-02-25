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
            f.write(f"""import os
import sys
import datetime
import json

LOG_FILE = os.path.expanduser('~/.gemini/hooks/ledgermind_debug.log')
PROJECT_PATH = '{project_path}'

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
    
    stdin_data = ''
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read()
            log_debug(f'Captured stdin (length: {{len(stdin_data)}})')
        except Exception as e:
            log_debug(f'Error reading stdin: {{str(e)}}')

    project_src = os.path.join(PROJECT_PATH, 'src')
    if os.path.exists(project_src) and project_src not in sys.path:
        sys.path.insert(0, project_src)

    try:
        from ledgermind.core.api.bridge import IntegrationBridge
        bridge = IntegrationBridge(memory_path=os.path.join(PROJECT_PATH, '.ledgermind'))
        
        action = sys.argv[1] if len(sys.argv) > 1 else 'unknown'
        
        if action == 'before':
            log_debug('Processing BeforeAgent')
            if stdin_data:
                bridge.memory.process_event(source='user', kind='prompt', content=stdin_data)
                log_debug('Prompt recorded to episodic.db')
                
                context = bridge.get_context_for_prompt(stdin_data)
                if context:
                    sys.stdout.write(context + '\\n\\n')
                    log_debug('Context injected to stdout')

        elif action == 'after':
            log_debug('Processing AfterAgent')
            if stdin_data:
                try:
                    data = json.loads(stdin_data)
                    transcript_path = data.get("transcript_path")
                    if transcript_path and os.path.exists(transcript_path):
                        with open(transcript_path, 'r', encoding='utf-8') as f:
                            transcript = json.load(f)
                        
                        turns = transcript.get("messages", transcript.get("turns", []))
                        last_user_idx = -1
                        for i in range(len(turns) - 1, -1, -1):
                            if turns[i].get("type") == "user" or turns[i].get("role") == "user":
                                last_user_idx = i
                                break
                        
                        gemini_turns = turns[last_user_idx + 1:] if last_user_idx != -1 else []
                        if not gemini_turns and turns:
                            gemini_turns = [turns[-1]]

                        events_recorded = 0
                        for t in gemini_turns:
                            if t.get("type") in ["gemini", "agent", "assistant"] or t.get("role") in ["assistant", "agent", "gemini"]:
                                text_content = t.get("content", "").strip()
                                if text_content:
                                    bridge.memory.process_event(source='agent', kind='result', content=text_content)
                                    events_recorded += 1
                                
                                tool_calls = t.get("toolCalls", [])
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

                        if events_recorded == 0:
                            bridge.memory.process_event(source='agent', kind='result', content=stdin_data)
                        
                        log_debug(f'Separated {{events_recorded}} events recorded to episodic.db')
                    else:
                        bridge.memory.process_event(source='agent', kind='result', content=stdin_data)
                        log_debug('Raw response recorded to episodic.db')

                except Exception as e:
                    bridge.memory.process_event(source='agent', kind='result', content=stdin_data)
                    log_debug(f'Raw response recorded (fallback): {{e}}')

    except Exception as e:
        log_debug(f'Error in main: {{str(e)}}')

if __name__ == '__main__':
    main()
""")
        print(f"✓ Installed Gemini CLI hooks successfully.")


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

    def install(self, project_path: str):
        # 1. Физическая установка расширения LedgerMind
        self._install_extension_files(project_path)

        # 2. Roo Code (Cline) - settings path
        roo_path = os.path.join(self.global_storage, "saoudrizwan.claude-dev", "settings", "cline_mcp_settings.json")
        self._inject_mcp_config(roo_path, project_path, "Roo Code (Cline)")

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
            subprocess.run(["npm", "install"], cwd=ext_src, check=True, capture_output=True)
            subprocess.run(["npm", "run", "compile"], cwd=ext_src, check=True, capture_output=True)
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
        instructions = "Always check for the existence of '.ledgermind_context.md' in the project root. If it exists, read it at the beginning of every task to synchronize with the autonomous memory and previous decisions."
        
        data = {}
        if os.path.exists(path):
            try:
                with open(path, "r") as f: data = json.load(f)
            except: data = {}

        # Добавляем или обновляем инструкцию
        if "global" not in data: data["global"] = ""
        if instructions not in data["global"]:
            data["global"] = (data["global"] + "\n\n" + instructions).strip()
            
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  → Injected Hardcore Memory Policy into Custom Instructions.")

    def _inject_mcp_config(self, config_path: str, project_path: str, ext_name: str):
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
            "args": ["run", "--path", os.path.abspath(project_path)],
            "disabled": False
        }

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"  → Injected LedgerMind MCP into {ext_name} settings.")


def install_client(client_name: str, project_path: str):
    installers = {
        "claude": ClaudeInstaller,
        "cursor": CursorInstaller,
        "gemini": GeminiInstaller,
        "vscode": VSCodeInstaller,
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
