import pytest
import threading
from unittest.mock import MagicMock, patch
from ledgermind.server.server import MCPServer
from ledgermind.core.api.memory import Memory

def test_maintenance_thread_singleton():
    """Verify that multiple MCPServer instances don't start multiple maintenance threads in one process."""
    mock_memory = MagicMock(spec=Memory)
    
    # Reset the singleton flag
    MCPServer._maintenance_running = False
    
    with patch("threading.Thread") as mock_thread:
        # First instance should start the thread
        server1 = MCPServer(memory=mock_memory)
        assert mock_thread.call_count == 1
        
        # Second instance should NOT start a new thread
        server2 = MCPServer(memory=mock_memory)
        assert mock_thread.call_count == 1

def test_maintenance_loop_skips_if_locked():
    """Verify that the maintenance loop skips a cycle if the filesystem is locked by another process."""
    mock_memory = MagicMock()
    call_event = threading.Event()
    
    def on_acquire(*args, **kwargs):
        call_event.set()
        return False # Locked
    
    mock_memory.semantic._fs_lock.acquire.side_effect = on_acquire
    
    MCPServer._maintenance_running = False
    
    # Patch sleep to not wait 30 seconds
    with patch("ledgermind.server.server.time.sleep"):
        server = MCPServer(memory=mock_memory)
        
        # Wait for the call to happen
        called = call_event.wait(timeout=5)
        assert called, "Maintenance thread did not call acquire() within 5 seconds"
        
        # Verify acquire was called with correct arguments
        mock_memory.semantic._fs_lock.acquire.assert_any_call(exclusive=True, timeout=0)
