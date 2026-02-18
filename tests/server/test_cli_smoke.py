import subprocess
import sys
import os
import pytest

def run_cli(args):
    """Helper to run the ledgermind CLI in a subprocess."""
    # Use sys.executable to ensure we use the same python env
    # Add src to PYTHONPATH so we can import ledgermind
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.abspath("src")
    
    cmd = [sys.executable, "-m", "ledgermind.server.cli"] + args
    return subprocess.run(cmd, capture_output=True, text=True, env=env)

def test_cli_help():
    result = run_cli(["--help"])
    assert result.returncode == 0
    assert "Ledgermind MCP Server Launcher" in result.stdout

def test_cli_init_and_check(tmp_path):
    memory_path = str(tmp_path / ".ledgermind")
    
    # Test init
    result = run_cli(["init", "--path", memory_path])
    assert result.returncode == 0
    assert "Initialization complete" in result.stdout
    assert os.path.exists(memory_path)
    
    # Test check
    result = run_cli(["check", "--path", memory_path])
    assert result.returncode == 0
    assert "Environment is healthy" in result.stdout
    assert "Git Available: ✓" in result.stdout

def test_cli_stats(tmp_path):
    memory_path = str(tmp_path / ".ledgermind")
    run_cli(["init", "--path", memory_path])
    
    # Test stats
    result = run_cli(["stats", "--path", memory_path])
    assert result.returncode == 0
    assert "Memory Statistics" in result.stdout
    assert "Episodic Events" in result.stdout

def test_cli_verbose_logging(tmp_path):
    memory_path = str(tmp_path / ".ledgermind")
    run_cli(["init", "--path", memory_path])
    
    # Test check with verbose
    result = run_cli(["--verbose", "check", "--path", memory_path])
    assert result.returncode == 0
    # Should see some DEBUG logs in stderr due to setup_logging
    assert "DEBUG" in result.stderr
