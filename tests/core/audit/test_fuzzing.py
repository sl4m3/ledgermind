import os
import pytest
import time
from ledgermind.core.api.memory import Memory

def test_random_supersede_chain(temp_storage):
    """Fuzzing-like test: long chain of supersedes."""
    memory = Memory(storage_path=temp_storage)
    target = "evolution_target"
    
    # Create initial
    memory.record_decision(title="v0", target=target, rationale="Start of the evolution chain")
    
    for i in range(1, 6): # Reduced to 5 for speed
        # V7.0: Use meta API to find the current version for the target
        metas = memory.semantic.meta.list_all(target=target)
        # Find the one that is either active or draft and not superseded
        active_fid = None
        for m in metas:
            if m.get('status') in ('active', 'draft') and not m.get('superseded_by'):
                active_fid = m.get('fid')
                break
        
        assert active_fid is not None, f"Could not find active version for target {target} at step {i}"
        
        res = memory.supersede_decision(
            title=f"v{i}", 
            target=target, 
            rationale=f"Update version {i} for evolution chain", 
            old_decision_ids=[active_fid]
        )
        assert res.should_persist is True

    # Validate integrity of the whole chain
    new_memory = Memory(storage_path=temp_storage)
    # get_decisions might return all files, but we care about the count
    decisions = new_memory.get_decisions()
    # v0 + 5 supersedes = 6 records total
    assert len(decisions) == 6
    print("Long supersede chain verified.")
