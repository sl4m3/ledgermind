import pytest
import os
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import TrustBoundary

def test_trust_boundary_human_only(temp_storage):
    """Verify that AGENT cannot write decisions in HUMAN_ONLY mode."""
    memory = Memory(storage_path=temp_storage, trust_boundary=TrustBoundary.HUMAN_ONLY)
    
    # Agent recording decision
    res = memory.record_decision(title="Autonomous Choice", target="security", rationale="Because I can")
    
    # Rejected by Trust Boundary
    assert res.should_persist is False
    assert "Trust Boundary Violation" in res.reason
    
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
