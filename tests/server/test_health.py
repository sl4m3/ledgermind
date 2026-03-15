import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from ledgermind.server.health import app, set_memory

client = TestClient(app)

@pytest.fixture
def mock_memory():
    memory = MagicMock()

    # Mock episodic
    memory.episodic = MagicMock()
    memory.episodic.db_path = "/fake/db.sqlite"
    memory.episodic.count_events.return_value = 42

    # Mock semantic
    memory.semantic = MagicMock()
    memory.semantic.repo_path = "/fake/repo"
    memory.semantic.list_decisions.return_value = [{"id": "1"}, {"id": "2"}]

    # Mock background worker
    memory.background_worker = MagicMock()
    memory.background_worker.status = "running"
    memory.background_worker.last_run = "2023-01-01T00:00:00Z"
    memory.background_worker.errors = []

    # Mock storage path
    memory.storage_path = "/fake/storage"

    # Mock vector
    memory.vector = MagicMock()
    memory.vector._model = "loaded"
    memory.vector._doc_ids = ["doc1"]
    memory.vector._vectors = MagicMock()
    memory.vector._vectors.ndim = 2
    memory.vector._vectors.shape = (1, 128)

    # Mock git availability
    memory._git_available = True

    # Set the global memory in health.py
    set_memory(memory)
    yield memory
    # Cleanup after test
    set_memory(None)

def test_health_no_memory():
    set_memory(None)
    response = client.get("/")
    assert response.status_code == 503
    assert response.json()["detail"] == "Memory instance not initialized"

@patch("ledgermind.server.health._check_database")
@patch("ledgermind.server.health._check_filesystem")
@patch("ledgermind.server.health._check_git_repo")
@patch("ledgermind.server.health._check_vector_store")
def test_health_healthy(mock_vector, mock_git, mock_fs, mock_db, mock_memory):
    mock_db.return_value = {"accessible": True, "status": "healthy"}
    mock_fs.return_value = {"accessible": True, "size_bytes": 100}
    mock_git.return_value = {"accessible": True, "status": "healthy"}
    mock_vector.return_value = {"accessible": True, "status": "healthy"}

    response = client.get("/")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["components"]["memory"]["status"] == "available"
    assert data["components"]["episodic"]["status"] == "healthy"
    assert data["components"]["episodic"]["events_count"] == 42
    assert data["components"]["semantic"]["accessible"] is True
    assert data["components"]["semantic"]["decisions_count"] == 2
    assert data["components"]["git"]["status"] == "healthy"
    assert data["components"]["vector"]["status"] == "healthy"

@patch("ledgermind.server.health._check_database")
@patch("ledgermind.server.health._check_filesystem")
@patch("ledgermind.server.health._check_git_repo")
@patch("ledgermind.server.health._check_vector_store")
def test_health_unhealthy_component(mock_vector, mock_git, mock_fs, mock_db, mock_memory):
    # If one component is unhealthy, it should return 503
    mock_db.return_value = {"accessible": False, "error": "Disk full"}
    mock_fs.return_value = {"accessible": True, "size_bytes": 100}
    mock_git.return_value = {"accessible": True, "status": "healthy"}
    mock_vector.return_value = {"accessible": True, "status": "healthy"}

    response = client.get("/")
    assert response.status_code == 503
    data = response.json()["detail"]

    assert data["status"] == "unhealthy"
    assert data["components"]["episodic"]["accessible"] is False
    assert data["components"]["episodic"]["error"] == "Disk full"

def test_readiness_no_memory():
    set_memory(None)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "Memory instance not initialized"

def test_readiness_ready(mock_memory):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

def test_readiness_not_ready(mock_memory):
    # Make episodic store raise an error to simulate not ready
    mock_memory.episodic.count_events.side_effect = Exception("DB disconnected")
    response = client.get("/ready")
    assert response.status_code == 503
    data = response.json()["detail"]
    assert data["status"] == "not_ready"
    assert "DB disconnected" in data["error"]

def test_liveness():
    response = client.get("/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"

def test_dependencies(mock_memory):
    response = client.get("/dependencies")
    assert response.status_code == 200
    data = response.json()
    assert data["dependencies"]["git"]["status"] == "available"
    assert data["dependencies"]["vector_model"]["status"] == "loaded"

def test_dependencies_no_memory():
    set_memory(None)
    response = client.get("/dependencies")
    assert response.status_code == 200
    data = response.json()
    assert data["dependencies"]["git"]["status"] == "unavailable"
    assert "vector_model" not in data["dependencies"]
