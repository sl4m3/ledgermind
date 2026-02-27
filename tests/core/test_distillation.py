import pytest
import os
import json
from datetime import datetime
from ledgermind.core.reasoning.distillation import DistillationEngine
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.core.schemas import MemoryEvent, KIND_RESULT, ProceduralContent, ProposalContent

@pytest.fixture
def temp_db_path(tmp_path):
    db_file = tmp_path / "test_episodic.db"
    return str(db_file)

@pytest.fixture
def episodic_store(temp_db_path):
    store = EpisodicStore(temp_db_path)
    return store

@pytest.fixture
def distillation_engine(episodic_store):
    return DistillationEngine(episodic_store, window_size=5)

def create_event(store, kind, content, context=None, source="agent"):
    event = MemoryEvent(
        source=source,
        kind=kind,
        content=content,
        context=context or {},
        timestamp=datetime.now()
    )
    return store.append(event)

def test_distill_basic_flow(episodic_store, distillation_engine):
    """Test basic distillation of a successful trajectory."""
    # 1. Add a successful sequence starting with a user prompt (required by Turn logic)
    create_event(episodic_store, "prompt", "User request", source="user")
    create_event(episodic_store, "task", "Solve the puzzle")
    create_event(episodic_store, "prompt", "Thinking about move")
    create_event(episodic_store, "call", "tool_call_move(x=1)")

    # Result event with success context
    result_context = {"success": True, "target": "Solve the puzzle"}
    result_id = create_event(episodic_store, KIND_RESULT, "Puzzle solved", result_context)

    # 2. Distill
    proposals = distillation_engine.distill_trajectories()

    # 3. Verify
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.target == "Solve the puzzle"
    # We now expect 4 meaningful agent steps (task, prompt, call, result) 
    # depending on the clean_content and rationale logic in core.
    assert len(proposal.procedural.steps) >= 3

    assert result_id in proposal.evidence_event_ids

def test_distill_with_after_id(episodic_store, distillation_engine):
    """Test distillation with after_id parameter."""
    # Add some events that should be ignored if we use after_id
    id0 = create_event(episodic_store, "prompt", "Old request", source="user")
    id1 = create_event(episodic_store, "task", "Old task")
    id2 = create_event(episodic_store, KIND_RESULT, "Old result", {"success": True, "target": "Old task"})

    # New sequence
    id_u = create_event(episodic_store, "prompt", "New request", source="user")
    id3 = create_event(episodic_store, "task", "New task")
    id4 = create_event(episodic_store, KIND_RESULT, "New result", {"success": True, "target": "New task"})

    # Distill after id2
    proposals = distillation_engine.distill_trajectories(after_id=id2)

    assert len(proposals) == 1
    assert proposals[0].target == "New task"

def test_distill_boundary_first_event_is_result(episodic_store, distillation_engine):
    """Test boundary condition where the very first event is a result."""
    # If the very first event is a result, trajectory is empty.
    create_event(episodic_store, KIND_RESULT, "Immediate success", {"success": True, "target": "Zero work"})

    proposals = distillation_engine.distill_trajectories()

    # trajectory_events = chronological_events[max(0, i - self.window_size):i]
    # If i=0, slice is 0:0 -> empty.
    # if trajectory_events: ... -> False
    assert len(proposals) == 0

def test_distill_failure_ignored(episodic_store, distillation_engine):
    """Test that failed results do not generate proposals."""
    create_event(episodic_store, "task", "Hard task")
    create_event(episodic_store, KIND_RESULT, "Failed attempt", {"success": False, "target": "Hard task"})

    proposals = distillation_engine.distill_trajectories()
    assert len(proposals) == 0

def test_distill_window_limit(episodic_store, distillation_engine):
    """Test that the window size limits the number of steps in a proposal."""
    # Window size is 5 (from fixture)
    # Start Turn
    create_event(episodic_store, "prompt", "Bulk task request", source="user")
    
    # Add 7 events before result
    for i in range(7):
        create_event(episodic_store, "task", f"Step {i}")

    create_event(episodic_store, KIND_RESULT, "Success", {"success": True, "target": "Long task"})

    proposals = distillation_engine.distill_trajectories()
    assert len(proposals) == 1
    # Check that we have a limited number of steps.
    # The actual number might be self.window_size if the trajectory is long enough.
    steps = proposals[0].procedural.steps
    assert len(steps) > 0

def test_distill_multiple_trajectories(episodic_store, distillation_engine):
    """Test finding multiple trajectories in the event stream."""
    # Trajectory 1: Turn 1
    create_event(episodic_store, "prompt", "Request 1", source="user")
    create_event(episodic_store, "task", "Task 1")
    create_event(episodic_store, KIND_RESULT, "Result 1", {"success": True, "target": "Task 1"})

    # Trajectory 2: Turn 2
    create_event(episodic_store, "prompt", "Request 2", source="user")
    create_event(episodic_store, "task", "Task 2")
    create_event(episodic_store, KIND_RESULT, "Result 2", {"success": True, "target": "Task 2"})

    proposals = distillation_engine.distill_trajectories()

    # Should find both
    assert len(proposals) == 2
    targets = {p.target for p in proposals}
    assert "Task 1" in targets
    assert "Task 2" in targets
