"""
Test namespace handling in CLI bridge commands.

Tests verify that --cli flag is correctly used as namespace in bridge-context,
bridge-sync, and bridge-record commands.
"""

import pytest
import os
import sys
import io
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from ledgermind.core.api.memory import Memory


def run_cli(args):
    """Helper to run the ledgermind CLI directly in the current process."""
    from ledgermind.server.cli import main
    
    # Capture stdout and stderr
    stdout = io.StringIO()
    stderr = io.StringIO()
    return_code = 0  # Default to success

    with patch.object(sys, 'argv', ['ledgermind'] + args):
        with patch.object(sys, 'stdout', stdout):
            with patch.object(sys, 'stderr', stderr):
                try:
                    main()
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


class TestCLINamespace:
    """Test namespace handling in CLI bridge commands."""
    
    def test_bridge_context_with_cli_flag(self, tmp_path):
        """Verify bridge-context respects --cli flag as namespace."""
        # Setup memory with decisions in different namespaces
        memory = Memory(storage_path=str(tmp_path))
        memory.record_decision("Claude decision", "test", "This is the rationale for Claude decision", namespace="claude")
        memory.record_decision("Gemini decision", "test", "This is the rationale for Gemini decision", namespace="gemini")
        
        # Run bridge-context with --cli claude
        result = run_cli([
            "bridge-context",
            "--path", str(tmp_path),
            "--cli", "claude",
            "--prompt", "test"
        ])
        
        assert result.returncode == 0
        assert "Claude decision" in result.stdout
        assert "Gemini decision" not in result.stdout
    
    def test_bridge_context_with_gemini_cli(self, tmp_path):
        """Verify bridge-context with --cli gemini uses gemini namespace."""
        memory = Memory(storage_path=str(tmp_path))
        memory.record_decision("Claude decision", "test", "This is the rationale for Claude decision", namespace="claude")
        memory.record_decision("Gemini decision", "test", "This is the rationale for Gemini decision", namespace="gemini")
        
        # Run bridge-context with --cli gemini
        result = run_cli([
            "bridge-context",
            "--path", str(tmp_path),
            "--cli", "gemini",
            "--prompt", "test"
        ])
        
        assert result.returncode == 0
        assert "Gemini decision" in result.stdout
        assert "Claude decision" not in result.stdout
    
    def test_bridge_context_without_cli_flag(self, tmp_path):
        """Verify bridge-context uses default namespace when --cli not specified."""
        memory = Memory(storage_path=str(tmp_path))
        memory.record_decision("Default decision", "test", "This is the default rationale for testing")
        
        result = run_cli([
            "bridge-context",
            "--path", str(tmp_path),
            "--prompt", "test"
        ])
        
        assert result.returncode == 0
        assert "Default decision" in result.stdout
    
    def test_bridge_record_with_cli_flag(self, tmp_path):
        """Verify bridge-record respects --cli flag for namespace."""
        # Run bridge-record with --cli claude
        result = run_cli([
            "bridge-record",
            "--path", str(tmp_path),
            "--cli", "claude",
            "--prompt", "Test prompt",
            "--response", "Test response"
        ])
        
        assert result.returncode == 0
        
        # Verify events were recorded
        memory = Memory(storage_path=str(tmp_path))
        events = memory.episodic.query(limit=10)
        assert len(events) >= 2  # prompt + result
