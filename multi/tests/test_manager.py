import pytest
import sys
import os
# Добавляем путь к core, чтобы тесты multi могли найти api.memory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../core")))

from manager import MemoryMultiManager
from unittest.mock import MagicMock

def test_manager_init():
    manager = MemoryMultiManager()
    assert manager.core is None
    assert manager.get_tools("openai") is not None

def test_handle_tool_call_no_core():
    manager = MemoryMultiManager()
    result = manager.handle_tool_call("record_decision", {})
    assert result["status"] == "error"
    assert "not initialized" in result["message"]

def test_handle_tool_call_success():
    mock_core = MagicMock()
    manager = MemoryMultiManager(core_memory=mock_core)
    
    args = {"title": "Test", "target": "T", "rationale": "R"}
    manager.handle_tool_call("record_decision", args)
    
    mock_core.record_decision.assert_called_once_with(**args)
