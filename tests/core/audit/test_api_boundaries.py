import pytest
import os
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import TrustBoundary

from ledgermind.core.core.exceptions import InvariantViolation

def test_trust_boundary_human_only(temp_storage):
    """Verify that AGENT cannot write decisions in HUMAN_ONLY mode."""
    memory = Memory(storage_path=temp_storage, trust_boundary=TrustBoundary.HUMAN_ONLY)
    
    # Agent recording decision
    with pytest.raises(InvariantViolation) as excinfo:
        memory.record_decision(title="Autonomous Choice", target="security", rationale="Because I can")
    
    assert "Trust Boundary Violation" in str(excinfo.value)
    
    # Ensure nothing was saved to semantic
    sem_path = os.path.join(temp_storage, "semantic")
    if os.path.exists(sem_path):
        files = [f for f in os.listdir(sem_path) if f.endswith(".md")]
        assert len(files) == 0

def test_trust_boundary_agent_allowed(temp_storage):
    """Verify that default mode (AGENT_WITH_INTENT) allows recording."""
    memory = Memory(storage_path=temp_storage, trust_boundary=TrustBoundary.AGENT_WITH_INTENT)
    
    res = memory.record_decision(title="Autonomous Choice", target="security", rationale="Because I can")
    
    assert res.should_persist is True
    assert res.store_type == "semantic"
