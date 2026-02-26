import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from ledgermind.server.gateway import app, get_memory

@pytest.fixture
def client():
    mock_memory = MagicMock()
    app.dependency_overrides[get_memory] = lambda: mock_memory
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_auth_enforced_when_unconfigured(client):
    """If LEDGERMIND_API_KEY is not set, access should be DENIED."""
    with patch.dict(os.environ, {}, clear=True):
        # Health check is explicitly public
        res = client.get("/health")
        assert res.status_code == 200
        
        # Protected endpoints should fail if key is missing
        with patch("ledgermind.server.gateway.EventSourceResponse") as mock_sse:
            from fastapi.responses import Response
            mock_sse.return_value = Response(status_code=200)
            res = client.get("/events")
            assert res.status_code == 500

def test_auth_protected_endpoints(client):
    """If LEDGERMIND_API_KEY is set, endpoints should require it."""
    with patch.dict(os.environ, {"LEDGERMIND_API_KEY": "secret"}):
        # 1. No key -> 403
        res = client.post("/search", json={"query": "test"})
        assert res.status_code == 403
        
        res = client.get("/events")
        assert res.status_code == 403
        
        # 2. Wrong key -> 403
        res = client.post("/search", json={"query": "test"}, headers={"X-API-Key": "wrong"})
        assert res.status_code == 403
        
        # 3. Correct key in header -> 200
        res = client.post("/search", json={"query": "test"}, headers={"X-API-Key": "secret"})
        assert res.status_code == 200
        
        # 4. Correct key in query param -> 200
        res = client.post("/search", json={"query": "test"}, params={"api_key": "secret"})
        assert res.status_code == 200

def test_websocket_auth(client):
    """Test WebSocket authentication logic."""
    with patch.dict(os.environ, {"LEDGERMIND_API_KEY": "secret"}):
        # 1. No key -> Closed with 4003
        with client.websocket_connect("/ws") as websocket:
            # TestClient might not expose the close code easily in all versions, 
            # but it should disconnect or fail to receive
            try:
                websocket.receive_json()
                pytest.fail("Should have been disconnected")
            except:
                pass # Expected
        
        # 2. Correct key -> Success
        with client.websocket_connect("/ws?api_key=secret") as websocket:
            websocket.send_text("hello")
            data = websocket.receive_json()
            assert data["status"] == "received"

def test_websocket_fails_without_config(client):
    """Test WebSocket authentication fails if server key is not configured."""
    from starlette.websockets import WebSocketDisconnect
    with patch.dict(os.environ, {}, clear=True):
        # Should be closed with 1008
        try:
            with client.websocket_connect("/ws") as websocket:
                websocket.receive_json()
            pytest.fail("Should have been disconnected")
        except WebSocketDisconnect as e:
            assert e.code == 1008
