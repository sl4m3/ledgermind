import pytest
import time
import os
import threading
from agent_memory_runner.pty_driver import PTYDriver

def test_pty_lifecycle():
    """Verify that PTYDriver starts and stops correctly."""
    exit_called = False
    def on_exit():
        nonlocal exit_called
        exit_called = True

    # Use a quick command
    driver = PTYDriver(["echo", "ok"])
    driver.run(on_output=lambda d: None, on_exit=on_exit)
    
    # Wait for process to finish
    time.sleep(0.5)
    assert exit_called
