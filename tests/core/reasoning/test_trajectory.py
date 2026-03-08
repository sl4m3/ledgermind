
import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.schemas import MemoryEvent
from ledgermind.core.core.targets import TargetRegistry
from ledgermind.core.reasoning.trajectory import TrajectoryBuilder

@pytest.fixture
def target_registry(tmp_path):
    registry = TargetRegistry(str(tmp_path))
    registry.register("core/api", "Core API")
    registry.register("vcs/git", "Git Version Control")
    return registry

@pytest.fixture
def builder(target_registry):
    return TrajectoryBuilder(target_registry)

def test_hierarchical_normalization(target_registry):
    """Test that TargetRegistry resolves suffixes correctly (V5.0)."""
    # Exact match
    assert target_registry.normalize("core/api") == "core/api"
    # Suffix match
    assert target_registry.normalize("api") == "core/api"
    assert target_registry.normalize("git") == "vcs/git"
    # No match returns original
    assert target_registry.normalize("unknown_thing") == "unknown_thing"

def test_atom_segmentation(builder):
    """Test that events are sliced into atoms based on user prompts."""
    events = [
        {"id": 1, "source": "user", "kind": "prompt", "content": "Hello", "timestamp": "2026-03-08T10:00:00Z"},
        {"id": 2, "source": "agent", "kind": "call", "content": "tool()", "timestamp": "2026-03-08T10:00:05Z"},
        {"id": 3, "source": "agent", "kind": "result", "content": "ok", "timestamp": "2026-03-08T10:00:10Z"},
        {"id": 4, "source": "user", "kind": "prompt", "content": "Next", "timestamp": "2026-03-08T10:05:00Z"},
        {"id": 5, "source": "agent", "kind": "call", "content": "tool2()", "timestamp": "2026-03-08T10:05:05Z"}
    ]
    
    chains = builder.build_chains(events)
    assert len(chains) == 1 # They are within 1 hour, so 1 chain
    assert len(chains[0].atoms) == 2 # But 2 separate atoms (2 user prompts)
    assert chains[0].atoms[0].events[0].content == "Hello"
    assert chains[0].atoms[1].events[0].content == "Next"

def test_target_deduction_from_paths(builder):
    """Test that target is correctly deduced from file paths in tool calls."""
    events = [
        {"id": 1, "source": "user", "kind": "prompt", "content": "Fix api"},
        {"id": 2, "source": "agent", "kind": "call", "content": "Reading src/core/api/memory.py"},
        {"id": 3, "source": "agent", "kind": "result", "content": "Found bug in src/core/api/memory.py"}
    ]
    # Set fixed timestamps to ensure they form a chain
    now = datetime.now()
    for i, e in enumerate(events):
        e['timestamp'] = (now + timedelta(seconds=i)).isoformat()

    chains = builder.build_chains(events)
    assert len(chains) == 1
    # Deduceed: src/core/api -> core/api -> normalized to core/api
    assert chains[0].global_target == "core/api"

def test_target_fallback_to_decision_id(builder):
    """Test that target falls back to decision_id if no paths are found."""
    did = "8dfe2633-3305-48ed-8d11-1db521211659"
    events = [
        {"id": 1, "source": "user", "kind": "prompt", "content": "Update thing"},
        {"id": 2, "source": "agent", "kind": "call", "content": "some action", "context": {"decision_id": did}},
        {"id": 3, "source": "agent", "kind": "result", "content": "done", "context": {"decision_id": did}}
    ]
    now = datetime.now()
    for i, e in enumerate(events):
        e['timestamp'] = (now + timedelta(seconds=i)).isoformat()

    chains = builder.build_chains(events)
    assert chains[0].global_target == f"Recovered-{did[:8]}"

def test_chain_linking_by_time(builder):
    """Test that atoms far apart in time form different chains."""
    events = [
        {"id": 1, "source": "user", "kind": "prompt", "content": "Morning", "timestamp": "2026-03-08T08:00:00Z"},
        {"id": 2, "source": "agent", "kind": "result", "content": "done", "timestamp": "2026-03-08T08:00:05Z"},
        {"id": 3, "source": "user", "kind": "prompt", "content": "Evening", "timestamp": "2026-03-08T20:00:00Z"},
        {"id": 4, "source": "agent", "kind": "result", "content": "done", "timestamp": "2026-03-08T20:00:05Z"}
    ]
    
    chains = builder.build_chains(events)
    assert len(chains) == 2 # > 1 hour gap
    assert chains[0].atoms[0].events[0].content == "Morning"
    assert chains[1].atoms[0].events[0].content == "Evening"
