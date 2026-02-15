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
    req = RecordDecisionRequest(title="Test Decision", target="T", rationale="Reason must be at least 10 chars", consequences=[])
    
    response = server.handle_record_decision(req)
    assert response.status == "error"
    assert "Permission denied" in response.message
    mock_memory.record_decision.assert_not_called()

def test_admin_accept_allowed(mock_memory):
    server = MCPServer(memory=mock_memory, default_role=MCPRole.ADMIN)
    req = AcceptProposalRequest(proposal_id="test.md")
    response = server.handle_accept_proposal(req)
    # Response is from Pydantic model dump json? No, handle_accept returns BaseResponse
    assert response.status == "success"
    mock_memory.accept_proposal.assert_called_once()

def test_token_auth_fallback(tmp_path):
    # Test the serve() logic for token requirement
    storage = str(tmp_path)
    os.environ.pop("AGENT_MEMORY_SECRET", None)
    
    # We patch Memory to avoid real git/sqlite init
    with patch("agent_memory_core.api.memory.Memory"):
        with patch("mcp.server.fastmcp.FastMCP"):
            # If secret is missing, role should downgrade to viewer
            # We need to capture stderr to verify
            with patch("sys.stderr") as mock_stderr:
                from agent_memory_server.server import MCPServer
                # Mocking run() to avoid blocking
                with patch.object(MCPServer, 'run'):
                    MCPServer.serve(storage_path=storage, role="admin")
                    # Check if warning was printed
                    args, _ = mock_stderr.write.call_args_list[0]
                    assert "SECURITY ERROR" in args[0]

from unittest.mock import patch
