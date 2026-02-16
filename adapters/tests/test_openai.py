import json
import pytest
from unittest.mock import MagicMock
from agent_memory_adapters.openai import OpenAIAdapter

class MockToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = MagicMock()
        self.function.name = name
        self.function.arguments = json.dumps(arguments)

def test_openai_process_tool_calls():
    # Mock MemoryProvider
    mock_memory = MagicMock()
    mock_memory.record_decision.return_value = {"status": "success", "metadata": {"file_id": "dec_123.md"}}
    
    adapter = OpenAIAdapter(mock_memory)
    
    # Simulate a tool call for record_decision
    tool_calls = [
        MockToolCall("call_1", "record_decision", {
            "title": "Test Decision",
            "target": "testing",
            "rationale": "For unit testing"
        })
    ]
    
    results = adapter.process_tool_calls(tool_calls)
    
    assert len(results) == 1
    assert results[0]["tool_call_id"] == "call_1"
    assert results[0]["name"] == "record_decision"
    
    content = json.loads(results[0]["content"])
    assert content["status"] == "success"
    assert content["data"]["metadata"]["file_id"] == "dec_123.md"
    
    mock_memory.record_decision.assert_called_once_with(
        title="Test Decision",
        target="testing",
        rationale="For unit testing"
    )

def test_openai_invalid_json():
    mock_memory = MagicMock()
    adapter = OpenAIAdapter(mock_memory)
    
    tool_call = MockToolCall("call_2", "some_method", {})
    tool_call.function.arguments = "invalid json"
    
    results = adapter.process_tool_calls([tool_call])
    
    assert len(results) == 1
    content = json.loads(results[0]["content"])
    assert content["status"] == "error"
    assert "Invalid JSON" in content["message"]

def test_openai_method_not_found():
    mock_memory = MagicMock(spec=[]) # No methods allowed
    adapter = OpenAIAdapter(mock_memory)
    
    tool_call = MockToolCall("call_3", "non_existent", {})
    results = adapter.process_tool_calls([tool_call])
    
    assert len(results) == 1
    content = json.loads(results[0]["content"])
    assert content["status"] == "error"
