import pytest
from unittest.mock import MagicMock
from agent_memory_adapters.google import GoogleAdapter
from agent_memory_adapters.ollama import OllamaAdapter

class MockGoogleToolCall:
    def __init__(self, name, args):
        self.function_call = MagicMock()
        self.function_call.name = name
        self.function_call.args = args

class MockOllamaToolCall:
    def __init__(self, name, args):
        self.function = MagicMock()
        self.function.name = name
        self.function.arguments = args

def test_google_adapter():
    mock_memory = MagicMock()
    mock_memory.record_decision.return_value = {"id": "g1"}
    
    adapter = GoogleAdapter(mock_memory)
    tool_calls = [MockGoogleToolCall("record_decision", {"title": "T", "target": "T", "rationale": "R"})]
    
    results = adapter.handle_tool_calls(tool_calls)
    assert len(results) == 1
    assert results[0]["function_name"] == "record_decision"
    assert results[0]["response"]["result"]["id"] == "g1"

def test_ollama_adapter():
    mock_memory = MagicMock()
    mock_memory.search_decisions.return_value = []
    
    adapter = OllamaAdapter(mock_memory)
    tool_calls = [MockOllamaToolCall("search_decisions", {"query": "q"})]
    
    results = adapter.process_tool_calls(tool_calls)
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert results[0]["name"] == "search_decisions"
