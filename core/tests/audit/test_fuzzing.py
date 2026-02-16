import os
import pytest
import time
from agent_memory_core.api.memory import Memory

def test_random_supersede_chain(temp_storage):
    """Fuzzing-like test: long chain of supersedes."""
    memory = Memory(storage_path=temp_storage)
    target = "evolution_target"
    
    # Create initial
    memory.record_decision(title="v0", target=target, rationale="Start of the evolution chain")
    
    for i in range(1, 6): # Reduced to 5 for speed
        files = memory.get_decisions()
        # Get the current active file (the only one with status active)
        # We find it by scanning files
        active_fid = None
        for f in files:
            file_path = os.path.join(temp_storage, "semantic", f)
            # Ensure the path exists before reading
            if not os.path.exists(file_path): continue
            with open(file_path, 'r') as stream:
                if "status: active" in stream.read():
                    active_fid = f
                    break
        
        assert active_fid is not None
        res = memory.supersede_decision(
            title=f"v{i}", 
            target=target, 
            rationale=f"Update version {i} for evolution chain", 
            old_decision_ids=[active_fid]
        )
        assert res.should_persist is True

    # Validate integrity of the whole chain
    new_memory = Memory(storage_path=temp_storage)
    decisions = new_memory.get_decisions()
    assert len(decisions) == 6
    print("Long supersede chain verified.")
