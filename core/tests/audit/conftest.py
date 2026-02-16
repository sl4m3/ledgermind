import pytest
import shutil
import os
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import EmbeddingProvider

class MockEmbeddingProvider(EmbeddingProvider):
    def get_embedding(self, text: str):
        return [0.1] * 1536

@pytest.fixture
def temp_storage(tmp_path):
    storage = tmp_path / "memory"
    return str(storage)

@pytest.fixture
def mock_embedding_provider():
    return MockEmbeddingProvider()

@pytest.fixture
def memory(temp_storage, mock_embedding_provider):
    return Memory(storage_path=temp_storage, embedding_provider=mock_embedding_provider)
