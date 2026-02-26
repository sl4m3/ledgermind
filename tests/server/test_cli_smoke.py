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
    memory_path = str(tmp_path / "ledgermind")
    run_cli(["init", "--path", memory_path])
    
    # Test stats
    result = run_cli(["stats", "--path", memory_path])
    assert result.returncode == 0
    assert "Memory Statistics" in result.stdout
    assert "Episodic Events" in result.stdout

def test_cli_verbose_logging(tmp_path):
    memory_path = str(tmp_path / "ledgermind")
    run_cli(["init", "--path", memory_path])
    
    # Test check with verbose
    result = run_cli(["--verbose", "check", "--path", memory_path])
    assert result.returncode == 0
    # Should see some DEBUG logs in stderr due to setup_logging
    assert "DEBUG" in result.stderr
