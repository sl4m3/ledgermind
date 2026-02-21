import pytest
import shutil
import os
from unittest.mock import MagicMock
import sys
import subprocess
from ledgermind.core.api.memory import Memory

@pytest.fixture(scope="session", autouse=True)
def mock_ml_models():
    """Globally mock heavy ML dependencies for the entire test session."""
    mock_st = MagicMock()
    # Mock SentenceTransformer class
    mock_st_class = MagicMock(return_value=mock_st)
    
    # Apply mocks to sys.modules
    sys.modules["sentence_transformers"] = MagicMock()
    sys.modules["sentence_transformers"].SentenceTransformer = mock_st_class
    
    import ledgermind.core.stores.vector
    ledgermind.core.stores.vector.EMBEDDING_AVAILABLE = True
    
    yield mock_st_class

@pytest.fixture(scope="session")
def base_repo_template(tmp_path_factory):
    """Creates a pre-initialized git repository to be used as a template."""
    base_dir = tmp_path_factory.mktemp("base_repo")
    sem_path = base_dir / "semantic"
    sem_path.mkdir()
    
    # Initial git setup
    subprocess.run(["git", "init", "--quiet"], cwd=str(sem_path), check=True)
    subprocess.run(["git", "config", "user.name", "test-user"], cwd=str(sem_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(sem_path), check=True)
    
    gitignore_path = sem_path / ".gitignore"
    gitignore_path.write_text("\n.lock\n.quarantine/\n.tx_backup/\n")
    
    subprocess.run(["git", "add", ".gitignore"], cwd=str(sem_path), check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "Initial"], cwd=str(sem_path), check=True)
    
    # Create episodic.db template if needed (optional optimization)
    
    return base_dir

@pytest.fixture
def temp_storage(tmp_path, base_repo_template):
    """Provides a fresh storage path by copying the base template."""
    storage = tmp_path / "memory"
    # Copy the whole template structure
    shutil.copytree(base_repo_template, storage)
    return str(storage)

@pytest.fixture
def memory(temp_storage):
    return Memory(storage_path=temp_storage, vector_workers=1)

