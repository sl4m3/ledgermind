import pytest
import os
from ledgermind.core.api.memory import Memory

from ledgermind.core.core.exceptions import InvariantViolation

def test_record_decision_persists(temp_storage):
    """Verify that record_decision persists to semantic store (no trust boundary)."""
    memory = Memory(storage_path=temp_storage)

    res = memory.record_decision(title="Autonomous Choice", target="security", rationale="Because I can")

    assert res.should_persist is True
    assert res.store_type == "semantic"

    # Ensure file was saved to semantic
    sem_path = os.path.join(temp_storage, "semantic")
    assert os.path.exists(sem_path)
    files = [f for f in os.listdir(sem_path) if f.endswith(".md")]
    assert len(files) == 1

def test_record_decision_basic(temp_storage):
    """Verify that default Memory allows recording without trust boundary."""
    memory = Memory(storage_path=temp_storage)

    res = memory.record_decision(title="Autonomous Choice", target="security", rationale="Because I can")

    assert res.should_persist is True
    assert res.store_type == "semantic"
