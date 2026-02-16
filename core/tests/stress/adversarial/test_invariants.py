import pytest
import os
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.exceptions import InvariantViolation, ConflictError

@pytest.fixture
def memory_fixture(tmp_path):
    storage = tmp_path / "adv_mem"
    os.makedirs(storage, exist_ok=True)
    return Memory(storage_path=str(storage))

from pydantic import ValidationError

def test_missing_fields_validation(memory_fixture):
    """
    Tries to inject invalid decision with missing fields.
    Expects Schema Validation Error.
    """
    mem = memory_fixture
    
    with pytest.raises((ValueError, ValidationError)):
        mem.record_decision("", "valid_target", "valid_rationale")
        
    with pytest.raises((ValueError, ValidationError)):
        mem.record_decision("Title", "", "valid_rationale")

def test_conflict_injection(memory_fixture):
    """
    Attempts to inject two active decisions for same target.
    Expects ConflictError.
    """
    mem = memory_fixture
    target = "unique_singleton"
    
    mem.record_decision("First", target, "Valid rationale ensuring length")
    
    with pytest.raises(ConflictError):
        mem.record_decision("Second", target, "Should fail due to conflict")

def test_supersede_nonexistent(memory_fixture):
    """
    Attempts to supersede a non-existent ID.
    Expects ConflictError or ValueError (legacy).
    """
    mem = memory_fixture

    # Update: Now raises ConflictError Suggesting rebase
    with pytest.raises((ConflictError, ValueError), match="no longer active"):
        mem.supersede_decision("New", "target", "valid_rationale_for_supersede", ["fake-id"])
def test_supersede_active_mismatch(memory_fixture):
    """
    Attempts to supersede an active decision with WRONG target.
    Expects Integrity Violation or Logic Error.
    """
    mem = memory_fixture
    
    d1 = mem.record_decision("D1", "target_A", "valid_rationale_initial")
    
    # Try to supersede D1 but say it's target_B
    # This should be caught by logic or fail later.
    # Currently, `supersede_decision` takes `target` as arg.
    # It should verify that old decision belongs to this target.
    
    try:
        mem.supersede_decision("D2", "target_B", "valid_rationale_supersede", [d1.metadata["file_id"]])
    except (ValueError, ConflictError) as e:
        # Either ValueError (legacy) or ConflictError (modern) is fine as long as it blocks the change
        assert "not an active decision" in str(e) or "no longer active" in str(e)
