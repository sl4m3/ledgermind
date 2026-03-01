import os
import sys
import json
import pytest
import io
from unittest.mock import patch, MagicMock
from pathlib import Path
from ledgermind.server.cli import main

def run_cli(args):
    stdout = io.StringIO()
    stderr = io.StringIO()
    # Ensure we use a clean argv
    with patch.object(sys, 'argv', ['ledgermind'] + args):
        with patch.object(sys, 'stdout', stdout):
            with patch.object(sys, 'stderr', stderr):
                try:
                    main()
                    return_code = 0
                except SystemExit as e:
                    return_code = e.code if isinstance(e.code, int) else 0
                except Exception as e:
                    stderr.write(str(e))
                    return_code = 1
    
    class Result:
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode
            
    return Result(stdout.getvalue(), stderr.getvalue(), return_code)

@pytest.fixture
def mock_home(tmp_path):
    home = tmp_path / "fake_home"
    home.mkdir()
    return home

def test_install_claude_hooks(mock_home, tmp_path):
    project_path = tmp_path / "project"
    project_path.mkdir()
    run_cli(["init", "--path", str(project_path / "ledgermind")])

    with patch("pathlib.Path.home", return_value=mock_home):
        result = run_cli(["install", "claude", "--path", str(project_path)])
        if result.returncode != 0:
            sys.__stderr__.write(f"STDERR: {result.stderr}\n")
        assert result.returncode == 0
        assert "Installed Claude hooks locally in" in result.stdout
        # Verify files are in project dir, NOT global dir
        project_hooks_dir = project_path / ".claude" / "hooks"
        settings_file = mock_home / ".claude" / "settings.json"
        
        assert (project_hooks_dir / "ledgermind_before_prompt.sh").exists()
        assert (project_hooks_dir / "ledgermind_after_interaction.sh").exists()
        assert settings_file.exists()
        
        # Verify settings.json points to the project hooks and has the new matcher format
        with open(settings_file, "r") as f:
            settings = json.load(f)
            # Check UserPromptSubmit
            ups = settings["hooks"]["UserPromptSubmit"]
            assert isinstance(ups, list)
            assert ups[0]["matcher"] == "*"
            assert ups[0]["hooks"][0]["command"] == str(project_hooks_dir / "ledgermind_before_prompt.sh")
            
            # Check PostToolUse
            ptu = settings["hooks"]["PostToolUse"]
            assert isinstance(ptu, list)
            assert ptu[0]["matcher"] == "*"
            assert ptu[0]["hooks"][0]["command"] == str(project_hooks_dir / "ledgermind_after_interaction.sh")
        
        # Verify content
        before_content = (project_hooks_dir / "ledgermind_before_prompt.sh").read_text()
        assert "bridge-context" in before_content
        assert '--cli "claude"' in before_content
        assert ".ledgermind" in before_content

def test_install_cursor_hooks(mock_home, tmp_path):
    project_path = tmp_path / "project"
    project_path.mkdir()
    
    with patch("pathlib.Path.home", return_value=mock_home):
        result = run_cli(["install", "cursor", "--path", str(project_path)])
        if result.returncode != 0:
            sys.__stderr__.write(f"STDERR: {result.stderr}\n")
        assert result.returncode == 0
        assert "Installed Cursor hooks locally in" in result.stdout
        project_hooks_dir = project_path / ".ledgermind" / "hooks"
        hooks_file = mock_home / ".cursor" / "hooks.json"
        
        assert (project_hooks_dir / "ledgermind_before.sh").exists()
        assert hooks_file.exists()
        
        # Verify JSON points to the project hooks
        with open(hooks_file, "r") as f:
            config = json.load(f)
            assert str(project_hooks_dir / "ledgermind_before.sh") in config["beforeSubmitPrompt"]
        
        # Verify content
        before_content = (project_hooks_dir / "ledgermind_before.sh").read_text()
        assert "bridge-context" in before_content
        assert '--cli "cursor"' in before_content
        assert ".ledgermind" in before_content

        with open(hooks_file) as f:
            config = json.load(f)
            assert config["beforeSubmitPrompt"] == str(project_hooks_dir / "ledgermind_before.sh")

def test_install_gemini_hooks(mock_home, tmp_path):
    project_path = tmp_path / "project"
    project_path.mkdir()
    
    with patch("pathlib.Path.home", return_value=mock_home):
        result = run_cli(["install", "gemini", "--path", str(project_path)])
        if result.returncode != 0:
            sys.__stderr__.write(f"STDERR: {result.stderr}\n")
        assert result.returncode == 0
        assert "Installed Gemini CLI hooks successfully" in result.stdout

        project_hooks_dir = project_path / ".gemini" / "hooks"
        hook_file = project_hooks_dir / "ledgermind_hook.py"
        assert hook_file.exists()
        content = hook_file.read_text()
        assert "bridge.get_context_for_prompt" in content
        assert "IntegrationBridge(memory_path=MEMORY_PATH)" in content
        assert str(project_path) in content

def test_bridge_context_cli(tmp_path):
    memory_path = tmp_path / "ledgermind"
    run_cli(["init", "--path", str(memory_path)])
    
    # Record a decision first so we have context
    from ledgermind.core.api.memory import Memory
    mem = Memory(vector_model="v5-small-text-matching-Q4_K_M.gguf", storage_path=str(memory_path))
    mem.record_decision(title="Test Rule", target="test", rationale="Important decision for testing hooks")
    
    # Use a low threshold to ensure context injection regardless of exact similarity score
    result = run_cli(["bridge-context", "--path", str(memory_path), "--prompt", "Test Rule", "--threshold", "0.1"])
    if result.returncode != 0:
        sys.__stderr__.write(f"STDERR: {result.stderr}\n")
    assert result.returncode == 0
    assert "[LEDGERMIND KNOWLEDGE BASE ACTIVE]" in result.stdout
    assert "Test Rule" in result.stdout

def test_bridge_record_cli(tmp_path):
    memory_path = tmp_path / "ledgermind"
    run_cli(["init", "--path", str(memory_path)])
    
    result = run_cli([
        "bridge-record", 
        "--path", str(memory_path), 
        "--prompt", "hello", 
        "--response", "world",
        "--metadata", '{"model": "test-v1"}'
    ])
    if result.returncode != 0:
        sys.__stderr__.write(f"STDERR: {result.stderr}\n")
    assert result.returncode == 0
    
    # Verify it was recorded
    result = run_cli(["stats", "--path", str(memory_path)])
    assert "Episodic Events" in result.stdout
