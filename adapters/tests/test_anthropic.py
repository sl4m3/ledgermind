import json
import pytest
from unittest.mock import MagicMock
from agent_memory_adapters.anthropic import AnthropicAdapter

class MockContentBlock:
    def __init__(self, type, id, name, input):
        self.type = type
        self.id = id
        self.name = name
        self.input = input

def test_anthropic_process_tool_use():
    mock_memory = MagicMock()
    mock_memory.search_decisions.return_value = [{"id": "doc1", "score": 0.9}]
    
    adapter = AnthropicAdapter(mock_memory)
    
    blocks = [
        MockContentBlock("tool_use", "tu_1", "search_decisions", {"query": "test"})
    ]
    
    results = adapter.process_tool_use(blocks)
    
    assert len(results) == 1
    assert results[0]["type"] == "tool_result"
    assert results[0]["tool_use_id"] == "tu_1"
    
    content = json.loads(results[0]["content"])
    assert content[0]["id"] == "doc1"
    
    mock_memory.search_decisions.assert_called_once_with(query="test")

def test_anthropic_error():
    mock_memory = MagicMock()
    mock_memory.non_existent.side_effect = Exception("Not found")
    
    adapter = AnthropicAdapter(mock_memory)
    
    blocks = [
        MockContentBlock("tool_use", "tu_2", "non_existent", {})
    ]
    
    results = adapter.process_tool_use(blocks)
    
    assert len(results) == 1
    assert results[0]["is_error"] is True
    content = json.loads(results[0]["content"])
    assert "Not found" in content["message"]
