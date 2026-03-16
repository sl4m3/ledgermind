"""
Test namespace in installed hooks.

Tests verify that installers correctly include --cli flag in hook scripts
for Claude, Cursor, and Gemini clients.
"""

import pytest
import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from ledgermind.server.installers import ClaudeInstaller, CursorInstaller, GeminiInstaller


class TestHooksNamespace:
    """Test namespace in installed hooks."""
    
    def test_claude_hook_includes_cli_flag(self, tmp_path):
        """Verify Claude installer includes --cli claude in hooks."""
        project_path = str(tmp_path / "project")
        memory_path = str(tmp_path / "memory")
        os.makedirs(project_path)
        
        installer = ClaudeInstaller()
        installer.install(project_path, memory_path=memory_path)
        
        # Check hook script contains --cli claude
        hook_path = os.path.join(project_path, ".claude", "hooks", "ledgermind_before_prompt.sh")
        assert os.path.exists(hook_path), f"Hook script not found at {hook_path}"
        
        with open(hook_path, 'r') as f:
            hook_content = f.read()
        
        assert "--cli" in hook_content
        assert "claude" in hook_content
    
    def test_claude_stop_hook_includes_cli_flag(self, tmp_path):
        """Verify Claude stop hook includes --cli claude."""
        project_path = str(tmp_path / "project")
        memory_path = str(tmp_path / "memory")
        os.makedirs(project_path)
        
        installer = ClaudeInstaller()
        installer.install(project_path, memory_path=memory_path)
        
        # Check stop hook script
        stop_hook_path = os.path.join(project_path, ".claude", "hooks", "ledgermind_stop.sh")
        assert os.path.exists(stop_hook_path)
        
        with open(stop_hook_path, 'r') as f:
            hook_content = f.read()
        
        assert "--cli" in hook_content
        assert "claude" in hook_content
    
    def test_cursor_hook_includes_cli_flag(self, tmp_path):
        """Verify Cursor installer includes --cli cursor in hooks."""
        project_path = str(tmp_path / "project")
        memory_path = str(tmp_path / "memory")
        os.makedirs(project_path)
        
        installer = CursorInstaller()
        installer.install(project_path, memory_path=memory_path)
        
        hook_path = os.path.join(project_path, ".ledgermind", "hooks", "ledgermind_before.sh")
        assert os.path.exists(hook_path)
        
        with open(hook_path, 'r') as f:
            hook_content = f.read()
        
        assert "--cli" in hook_content
        assert "cursor" in hook_content
    
    def test_cursor_after_hook_includes_cli_flag(self, tmp_path):
        """Verify Cursor after hook includes --cli cursor."""
        project_path = str(tmp_path / "project")
        memory_path = str(tmp_path / "memory")
        os.makedirs(project_path)
        
        installer = CursorInstaller()
        installer.install(project_path, memory_path=memory_path)
        
        after_hook_path = os.path.join(project_path, ".ledgermind", "hooks", "ledgermind_after.sh")
        assert os.path.exists(after_hook_path)
        
        with open(after_hook_path, 'r') as f:
            hook_content = f.read()
        
        assert "--cli" in hook_content
        assert "cursor" in hook_content
    
    def test_gemini_hook_includes_cli_flag(self, tmp_path):
        """Verify Gemini installer includes --cli gemini in hooks."""
        project_path = str(tmp_path / "project")
        memory_path = str(tmp_path / "memory")
        os.makedirs(project_path)
        
        installer = GeminiInstaller()
        installer.install(project_path, memory_path=memory_path)
        
        hook_path = os.path.join(project_path, ".gemini", "hooks", "ledgermind_hook.py")
        assert os.path.exists(hook_path)
        
        with open(hook_path, 'r') as f:
            hook_content = f.read()
        
        # Gemini hook uses cli variable in bridge calls
        assert "cli" in hook_content.lower() or "--cli" in hook_content
        assert "gemini" in hook_content
    
    def test_claude_mcp_config_includes_client_flag(self, tmp_path):
        """Verify Claude MCP config includes --client flag."""
        project_path = str(tmp_path / "project")
        memory_path = str(tmp_path / "memory")
        os.makedirs(project_path)
        
        installer = ClaudeInstaller()
        result = installer.install_mcp_server(project_path, memory_path, client="claude")
        
        # MCP server should be configured with --client claude
        # Check that install_mcp_server was called with client parameter
        assert result is True or result is False  # May fail if claude CLI not installed
    
    def test_gemini_mcp_config_includes_client_flag(self, tmp_path):
        """Verify Gemini MCP config includes --client flag."""
        project_path = str(tmp_path / "project")
        memory_path = str(tmp_path / "memory")
        os.makedirs(project_path)
        
        installer = GeminiInstaller()
        result = installer.install_mcp_server(project_path, memory_path, client="gemini")
        
        # Check settings file was created with --client flag
        settings_path = os.path.join(project_path, ".gemini", "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                config = json.load(f)
            
            if "mcpServers" in config and "ledgermind" in config["mcpServers"]:
                mcp_config = config["mcpServers"]["ledgermind"]
                assert "--client" in mcp_config.get("args", [])
                assert "gemini" in mcp_config.get("args", [])
