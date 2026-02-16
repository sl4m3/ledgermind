import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock
from agent_memory_adapters.mcp_client import MCPMemoryProxy, SyncMCPMemoryProxy

@pytest.mark.asyncio
async def test_mcp_proxy_calls():
    # Mocking MCP Session
    mock_session = AsyncMock()
    
    # Mock return value from call_tool
    mock_content = MagicMock()
    mock_content.text = json.dumps({"status": "success", "id": "remote_123"})
    mock_result = MagicMock()
    mock_result.content = [mock_content]
    
    mock_session.call_tool.return_value = mock_result
    
    proxy = MCPMemoryProxy(mock_session)
    
    # 1. Test record_decision
    res = await proxy.record_decision(title="Remote", target="Target", rationale="Reason")
    assert res["status"] == "success"
    assert res["id"] == "remote_123"
    
    # 2. Test search_decisions (expects results field)
    mock_content.text = json.dumps({"status": "success", "results": [{"id": "r1"}]})
    res_search = await proxy.search_decisions(query="test")
    assert len(res_search) == 1
    assert res_search[0]["id"] == "r1"

def test_sync_proxy_wrapper():
    # We use a real loop but mock the async proxy
    mock_async = AsyncMock()
    mock_async.record_decision.return_value = {"status": "sync_success"}
    
    # Create sync proxy
    sync_proxy = SyncMCPMemoryProxy(mock_async)
    
    # Call synchronously
    res = sync_proxy.record_decision(title="T", target="T", rationale="R")
    assert res["status"] == "sync_success"
    assert mock_async.record_decision.called
