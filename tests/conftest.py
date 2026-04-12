"""
Pytest configuration for test isolation.

Ensures tests run in isolated environment without affecting the host system.
"""

import os
import sys
import pytest


# Set environment variables BEFORE any imports that might use them
os.environ["LEDGERMIND_BYPASS_HOOKS"] = "1"


@pytest.fixture(autouse=True)
def isolate_test_environment():
    """
    Automatically isolate each test from the host system.
    
    This fixture:
    - Sets LEDGERMIND_BYPASS_HOOKS to prevent hook execution
    - Restores original environment after test
    - Prevents tests from affecting the host system
    """
    # Store original environment
    original_env = dict(os.environ)
    
    # Ensure hooks are bypassed
    os.environ["LEDGERMIND_BYPASS_HOOKS"] = "1"
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
