import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from ledgermind.server.gateway import app, get_memory

def test_gateway_endpoints():
    mock_memory = MagicMock()
    mock_memory.search_decisions.return_value = [{"id": "d1", "score": 0.8}]
    mock_memory.record_decision.return_value.metadata = {"file_id": "new.md"}
    
    # Override dependency
    app.dependency_overrides[get_memory] = lambda: mock_memory
    
    client = TestClient(app)
    
    # 1. Health
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "alive"
    
    with patch.dict(os.environ, {"LEDGERMIND_API_KEY": "test-key"}):
        headers = {"X-API-Key": "test-key"}

        # 2. Search
        res = client.post("/search", json={"query": "test"}, headers=headers)
        assert res.status_code == 200
        assert res.json()["results"][0]["id"] == "d1"

        # 3. Record
        res = client.post("/record", json={
            "title": "Rest Title",
            "target": "Rest Target",
            "rationale": "Enough length for rationale"
        }, headers=headers)
        assert res.status_code == 200
        assert res.json()["id"] == "new.md"
    
    app.dependency_overrides.clear()
