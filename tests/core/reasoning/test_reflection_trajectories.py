
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from ledgermind.core.reasoning.reflection import ReflectionEngine
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore

@pytest.fixture
def mock_episodic():
    store = MagicMock(spec=EpisodicStore)
    return store

@pytest.fixture
def mock_semantic(tmp_path):
    # We need a real-ish semantic store to handle TargetRegistry
    repo_path = tmp_path / "semantic"
    repo_path.mkdir()
    store = MagicMock(spec=SemanticStore)
    store.repo_path = str(repo_path)
    store.meta = MagicMock()
    store.meta.list_all.return_value = []
    store.meta.get_config.return_value = "optimal"
    return store

@pytest.fixture
def engine(mock_episodic, mock_semantic):
    processor = MagicMock()
    return ReflectionEngine(mock_episodic, mock_semantic, processor=processor)

def test_reflection_uses_deduced_targets(engine, mock_episodic, mock_semantic):
    """Verify that ReflectionEngine can now discover patterns without explicit targets."""
    
    # 1. Mock events WITHOUT targets, but WITH file paths in content
    # Total weight should be >= 1.0 to trigger proposal creation
    events = [
        {"id": 1, "source": "user", "kind": "prompt", "content": "Fix api", "timestamp": "2026-03-08T10:00:00Z"},
        {"id": 2, "source": "agent", "kind": "call", "content": "Reading src/core/api/memory.py", "timestamp": "2026-03-08T10:00:05Z"},
        {"id": 3, "source": "agent", "kind": "call", "content": "Writing src/core/api/memory.py", "timestamp": "2026-03-08T10:00:10Z"},
        {"id": 4, "source": "agent", "kind": "result", "content": "Fixed src/core/api/memory.py", "context": {"success": True}, "timestamp": "2026-03-08T10:00:15Z"},
        {"id": 5, "source": "agent", "kind": "error", "content": "Transient issue during fix", "timestamp": "2026-03-08T10:00:20Z"}
    ]
    mock_episodic.query.return_value = events
    
    # 2. Run reflection cycle
    # We need to mock the transaction context manager
    mock_semantic.transaction.return_value.__enter__.return_value = None
    
    # Pre-register the target to help normalization
    engine.target_registry.register("core/api", "Core API")
    
    ids, _ = engine.run_cycle(after_id=0)
    
    # 3. Assertions
    # It should have called _create_pattern_stream or _process_stream for 'core/api'
    # Even though NONE of the events had 'target': 'core/api'
    assert engine.processor.process_event.called
    args, kwargs = engine.processor.process_event.call_args
    assert kwargs["kind"] == "proposal"
    assert kwargs["context"].target == "core/api"
