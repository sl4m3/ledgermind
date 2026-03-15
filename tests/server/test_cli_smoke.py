import sys
import os
import pytest
import io
from unittest.mock import patch
from ledgermind.server.cli import main

def run_cli(args):
    """Helper to run the ledgermind CLI directly in the current process."""
    # Capture stdout and stderr
    stdout = io.StringIO()
    stderr = io.StringIO()
    
    # We patch sys.argv to simulate the command line arguments
    # and sys.stdout/stderr to capture output
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

def test_cli_help():
    result = run_cli(["--help"])
    assert result.returncode == 0
    assert "Ledgermind MCP Server Launcher" in result.stdout

def test_cli_init_and_check(tmp_path):
    memory_path = str(tmp_path / "ledgermind")

    # Test init
    with patch('ledgermind.server.cli.questionary.text') as mock_text, \
         patch('ledgermind.server.cli.questionary.select') as mock_select, \
         patch('ledgermind.server.cli.questionary.confirm') as mock_confirm:
        # Mock answers: Project Path, Memory Path, Language
        mock_text.return_value.ask.side_effect = [str(tmp_path), memory_path, "russian", "openai/gpt-4"]
        # Mock answers: Embedder, Provider, Client, Mode
        mock_select.return_value.ask.side_effect = ["jina-v5-4bit", "cli", "none", "lite"]
        # Mock confirm (for OpenRouter retry)
        mock_confirm.return_value.ask.side_effect = [False]  # Skip OpenRouter retry
        result = run_cli(["init", "--path", memory_path])

    assert result.returncode == 0, f"init failed: {result.stderr}"
    assert "Initialization complete" in result.stdout
    assert os.path.exists(memory_path)
    
    # Test check
    result = run_cli(["check", "--path", memory_path])
    assert result.returncode == 0
    assert "Environment is healthy" in result.stdout
    assert "Git Available: ✓" in result.stdout

def test_cli_stats(tmp_path):
    memory_path = str(tmp_path / "ledgermind")
    with patch('ledgermind.server.cli.questionary.text') as mock_text, \
         patch('ledgermind.server.cli.questionary.select') as mock_select:
        mock_text.return_value.ask.side_effect = [str(tmp_path), memory_path]
        mock_select.return_value.ask.side_effect = ["jina-v5-4bit", "none", "lite"]
        run_cli(["init", "--path", memory_path])
    
    # Test stats
    result = run_cli(["stats", "--path", memory_path])
    assert result.returncode == 0
    assert "Memory Statistics" in result.stdout
    assert "Episodic Events" in result.stdout

def test_cli_verbose_logging(tmp_path):
    memory_path = str(tmp_path / "ledgermind")
    with patch('ledgermind.server.cli.questionary.text') as mock_text, \
         patch('ledgermind.server.cli.questionary.select') as mock_select:
        mock_text.return_value.ask.side_effect = [str(tmp_path), memory_path]
        mock_select.return_value.ask.side_effect = ["jina-v5-4bit", "none", "lite"]
        run_cli(["init", "--path", memory_path])
    
    # Test check with verbose
    result = run_cli(["--verbose", "check", "--path", memory_path])
    assert result.returncode == 0
    # Should see some DEBUG logs in stderr due to setup_logging
    assert "DEBUG" in result.stderr

def test_cli_settings(tmp_path):
    memory_path = str(tmp_path / "ledgermind")
    # Initialize first
    with patch('ledgermind.server.cli.questionary.text') as mock_text, \
         patch('ledgermind.server.cli.questionary.select') as mock_select:
        mock_text.return_value.ask.side_effect = [str(tmp_path), memory_path]
        mock_select.return_value.ask.side_effect = ["jina-v5-4bit", "none", "rich"]
        run_cli(["init", "--path", memory_path])
    
    # Test settings show
    result = run_cli(["settings", "show", "--storage", memory_path])
    assert result.returncode == 0
    assert "LedgerMind Settings" in result.stdout
    assert "enrichment_mode" in result.stdout
    
    # Test settings get
    result = run_cli(["settings", "get", "enrichment_mode", "--storage", memory_path])
    assert result.returncode == 0
    assert "rich" in result.stdout
    
    # Test settings set
    result = run_cli(["settings", "set", "merge_threshold", "0.9", "--storage", memory_path])
    assert result.returncode == 0
    assert "updated to '0.9'" in result.stdout
    
    # Verify change
    result = run_cli(["settings", "get", "merge_threshold", "--storage", memory_path])
    assert result.returncode == 0
    assert "0.9" in result.stdout

    # Test settings (no subcommand) - should not raise AttributeError
    # We patch cmd_settings_interactive since it's interactive
    with patch('ledgermind.server.settings.cmd_settings_interactive') as mock_interactive:
        result = run_cli(["settings", "--storage", memory_path])
        assert result.returncode == 0
        mock_interactive.assert_called_once()

