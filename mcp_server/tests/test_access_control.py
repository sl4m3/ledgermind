import json
import os
import pytest
from unittest.mock import MagicMock
from agent_memory_server.server import MCPServer, MCPRole
from agent_memory_core.api.memory import Memory
from agent_memory_server.contracts import RecordDecisionRequest, AcceptProposalRequest

@pytest.fixture
def mock_memory(tmp_path):
    m = MagicMock(spec=Memory)
    m.storage_path = str(tmp_path)
    # Mock semantic store for commit hash retrieval
    m.semantic = MagicMock()
    m.semantic.get_head_hash.return_value = "mock_hash_123"
    return m

@pytest.fixture(autouse=True)
def set_auth_token():
    os.environ["AGENT_MEMORY_SECRET"] = "access-test-secret"
    yield
    os.environ.pop("AGENT_MEMORY_SECRET", None)

def test_viewer_write_denied(mock_memory):
    server = MCPServer(memory=mock_memory, default_role=MCPRole.VIEWER)
    req = RecordDecisionRequest(title="Test Decision", target="TargetArea", rationale="Reason must be at least 10 chars", consequences=[])
    
    response = server.handle_record_decision(req)
    assert response.status == "error"
    assert "Permission denied" in response.message
    mock_memory.record_decision.assert_not_called()

def test_capability_mode_bypass_secret(mock_memory):
    """Verify that explicit capabilities bypass the mandatory secret check."""
    os.environ.pop("AGENT_MEMORY_SECRET", None)
    # Start server with explicit capabilities - should NOT downgrade to viewer even without secret
    server = MCPServer(memory=mock_memory, capabilities={"propose": True})
    
    req = RecordDecisionRequest(title="Test", target="TargetArea", rationale="Long enough rationale string", consequences=[])
    server.handle_record_decision(req)
    # If we got here and record_decision was called, it means auth check passed
    mock_memory.record_decision.assert_called_once()

def test_admin_accept_allowed(mock_memory):
    server = MCPServer(memory=mock_memory, default_role=MCPRole.ADMIN)
    req = AcceptProposalRequest(proposal_id="test.md")
    response = server.handle_accept_proposal(req)
    # Response is from Pydantic model dump json? No, handle_accept returns BaseResponse
    assert response.status == "success"
    mock_memory.accept_proposal.assert_called_once()

from unittest.mock import patch
