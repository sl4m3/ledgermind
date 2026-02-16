import pytest
from unittest.mock import MagicMock
from agent_memory_adapters.crewai import RecordDecisionTool, SupersedeDecisionTool

def test_crewai_tools_direct():
    mock_memory = MagicMock()
    mock_memory.record_decision.return_value = "success_id"
    
    # Since we might not have crewai installed, the tool inherits from our mock BaseTool
    tool = RecordDecisionTool()
    tool.memory = mock_memory
    
    res = tool._run(title="T", target="Target", rationale="R")
    assert res == "success_id"
    mock_memory.record_decision.assert_called_once()

def test_crewai_supersede_tool():
    mock_memory = MagicMock()
    mock_memory.supersede_decision.return_value = "new_id"
    
    tool = SupersedeDecisionTool()
    tool.memory = mock_memory
    
    res = tool._run(title="T", target="Target", rationale="R", old_decision_ids=["old1"])
    assert res == "new_id"
    mock_memory.supersede_decision.assert_called_once()
