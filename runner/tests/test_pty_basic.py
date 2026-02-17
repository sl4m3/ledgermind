import os
import sys
import time
import pytest
from agent_memory_runner.pty_driver import PTYDriver

def test_pty_output_capture():
    """Verify that PTYDriver correctly captures output from a subprocess."""
    output_chunks = []
    
    def on_output(data):
        output_chunks.append(data)

    def on_exit():
        pass

    driver = PTYDriver(["echo", "hello_pty"])
    driver.run(on_output=on_output, on_exit=on_exit)
    
    combined_output = b"".join(output_chunks).decode()
    assert "hello_pty" in combined_output

def test_pty_initial_input():
    """Verify that initial_input is correctly sent to the subprocess."""
    output_chunks = []
    def on_output(data):
        output_chunks.append(data)

    # Use a command that reads one line and exits
    driver = PTYDriver(["head", "-n", "1"])
    driver.run(on_output=on_output, on_exit=lambda: None, initial_input=b"input_test\n")
    
    combined_output = b"".join(output_chunks).decode()
    assert "input_test" in combined_output
