import pytest
import shutil
import os
from agent_memory_core.api.memory import Memory

@pytest.fixture
def temp_storage(tmp_path):
    storage = tmp_path / "memory"
    return str(storage)

@pytest.fixture
def memory(temp_storage):
    return Memory(storage_path=temp_storage)

