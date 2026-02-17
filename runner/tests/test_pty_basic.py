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

    driver = PTYDriver(["echo", "-n", "hello_pty"])
    driver.run(on_output=on_output, on_exit=lambda: None)
    
    combined_output = b"".join(output_chunks).decode()
    assert "hello_pty" in combined_output

def test_pty_initial_input():
    """Verify that initial_input is correctly sent to the subprocess."""
    output_chunks = []
    def on_output(data):
        output_chunks.append(data)

    # Use 'cat' to echo initial input and exit
    # In PTY, we might need a newline to trigger some commands, or just use a command that reads till EOF
    driver = PTYDriver(["cat"])
    # We send input and then we'd need to close stdin, but in PTY we just wait for process to finish.
    # For a simple test, 'head -n 1' is better.
    driver = PTYDriver(["head", "-n", "1"])
    driver.run(on_output=on_output, on_exit=lambda: None, initial_input=b"input_test\n")
    
    combined_output = b"".join(output_chunks).decode()
    assert "input_test" in combined_output
