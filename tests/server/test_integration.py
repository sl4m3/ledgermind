import pytest
from unittest.mock import MagicMock, patch
import json
from ledgermind.server.server import MCPServer, MCPRole
from ledgermind.server.contracts import (
    RecordDecisionRequest, SupersedeDecisionRequest
)
from ledgermind.server.specification import MCPApiSpecification
from ledgermind.core.core.exceptions import ConflictError

@pytest.fixture
def mock_memory():
    mem = MagicMock()
    # Mock storage_path for session locking
    mem.storage_path = "/tmp/test_storage"
    
    # Mock Metadata Store for security audits
    mock_meta = MagicMock()
    mem.semantic.meta = mock_meta
    
    # Default behavior: Metadata exists and has required fields
    def get_meta_side_effect(fid):
        if fid == "human_1.md":
            return {
                "fid": "human_1.md", 
                "status": "active", 
                "title": "Human Decision",
                "content": "Rationale",
                "context_json": json.dumps({"provenance": "external", "source": "human"})
            }
        if fid == "mcp_1.md":
            return {
                "fid": "mcp_1.md", 
                "status": "active", 
                "title": "[via MCP] MCP Decision",
                "content": "Rationale",
                "context_json": json.dumps({"provenance": "internal", "source": "agent"})
            }
        if fid == "agent_1.md":
            return {
                "fid": "agent_1.md", 
                "status": "active", 
                "title": "Agent Decision",
                "content": "Rationale",
                "context_json": json.dumps({"provenance": "internal", "source": "agent"})
            }
        return None
        
    mock_meta.get_by_fid.side_effect = get_meta_side_effect
    return mem

def test_isolation_rule_enforcement(mock_memory):
    """Verify that an AGENT cannot supersede a HUMAN decision."""
    # MCP Server with AGENT role by default
    server = MCPServer(memory=mock_memory, default_role=MCPRole.AGENT, start_worker=False)
    
    human_decision_id = "human_1.md"
    
    req = SupersedeDecisionRequest(
        title="Agent Attempt",
        target="TargetArea",
        rationale="Trying to override with enough length",
        old_decision_ids=[human_decision_id]
    )
    
    response = server.handle_supersede_decision(req)
    assert response.status == "error"
    assert "Security Violation" in response.message
    mock_memory.supersede_decision.assert_not_called()

def test_agent_can_supersede_mcp_decision(mock_memory):
    """Verify that an AGENT CAN supersede an MCP-created decision."""
    server = MCPServer(memory=mock_memory, default_role=MCPRole.AGENT, start_worker=False)
    
    mcp_decision_id = "mcp_1.md"
    
    # CRITICAL: Return a real string ID instead of MagicMock
    mock_res = MagicMock()
    mock_res.metadata = {"file_id": "new_mcp_1.md"}
    mock_res.should_persist = True
    mock_memory.supersede_decision.return_value = mock_res
    
    req = SupersedeDecisionRequest(
        title="Agent Update",
        target="TargetArea",
        rationale="Updating my own knowledge with enough rationale",
        old_decision_ids=[mcp_decision_id]
    )
    
    response = server.handle_supersede_decision(req)
    assert response.status == "success"
    assert response.decision_id == "new_mcp_1.md"
    mock_memory.supersede_decision.assert_called_once()

def test_rate_limiting_cooldown(mock_memory):
    """Verify basic rate limiting or cooldown if implemented."""
    server = MCPServer(memory=mock_memory, default_role=MCPRole.AGENT, start_worker=False)
    server._write_cooldown = 0.0 # Disable cooldown for test
    
    # CRITICAL: Return real string ID
    mock_res = MagicMock()
    mock_res.metadata = {"file_id": "new_1.md"}
    mock_res.should_persist = True
    mock_memory.record_decision.return_value = mock_res
    
    req = RecordDecisionRequest(title="T1", target="Target", rationale="Rationale for testing rate limit")
    
    # Just ensure it doesn't crash on multiple calls
    for _ in range(5):
        server.handle_record_decision(req)
    
    assert mock_memory.record_decision.call_count == 5

def test_full_tool_registration():
    """Verify all tools are exposed via the specification."""
    spec = MCPApiSpecification.generate_full_spec()
    
    tool_names = spec["tools"].keys()
    assert "record_decision" in tool_names
    assert "supersede_decision" in tool_names
    assert "search_decisions" in tool_names
    assert "sync_git_history" in tool_names
