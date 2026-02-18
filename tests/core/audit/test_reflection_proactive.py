import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from ledgermind.core.reasoning.reflection import ReflectionEngine, ReflectionPolicy

def test_reflection_proactive_success():
    """Verify that consistent successes lead to best practice proposals."""
    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    
    # Simulate 6 successes for the same target
    mock_episodic.query.return_value = [
        {"id": i, "kind": "result", "content": "Success", "timestamp": datetime.now(), "context": {"target": "auth_flow"}}
        for i in range(6)
    ]
    
    # Mock semantic to return no existing decisions for this target
    mock_semantic.list_decisions.return_value = []
    
    policy = ReflectionPolicy(success_threshold=5)
    engine = ReflectionEngine(mock_episodic, mock_semantic, policy=policy)
    
    with patch.object(mock_semantic, "save", return_value="prop_123") as mock_save:
        results = engine.run_cycle()
        
        # Check if a proposal was created for the success pattern
        assert "prop_123" in results
        
        # Verify the content of the proposal
        args, _ = mock_save.call_args
        event = args[0]
        assert event.kind == "proposal"
        assert "Best Practice" in event.content
        assert event.context.target == "auth_flow"

def test_reflection_lower_error_threshold():
    """Verify that fewer errors now trigger a proposal in v4.1."""
    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    
    # Simulate 2 errors (new threshold is 2)
    mock_episodic.query.return_value = [
        {"id": 1, "kind": "error", "content": "Fail", "timestamp": datetime.now(), "context": {"target": "db_conn"}},
        {"id": 2, "kind": "error", "content": "Fail", "timestamp": datetime.now(), "context": {"target": "db_conn"}}
    ]
    
    mock_semantic.list_decisions.return_value = []
    
    policy = ReflectionPolicy(error_threshold=2)
    engine = ReflectionEngine(mock_episodic, mock_semantic, policy=policy)
    
    with patch.object(mock_semantic, "save", side_effect=["prop_err_1", "prop_err_2"]) as mock_save:
        results = engine.run_cycle()
        assert "prop_err_1" in results
        assert "prop_err_2" in results
        
        # Check that both competing hypotheses were saved
        assert mock_save.call_count >= 2
        
        saved_contents = [call.args[0].content for call in mock_save.call_args_list]
        assert any("Structural flaw" in c for c in saved_contents)
        assert any("Environmental noise" in c for c in saved_contents)

def test_reflection_skips_active_targets():
    """Verify that it doesn't suggest best practices for targets that already have active decisions."""
    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    
    mock_episodic.query.return_value = [
        {"id": i, "kind": "result", "content": "Success", "timestamp": datetime.now(), "context": {"target": "existing_target"}}
        for i in range(6)
    ]
    
    # Mock an existing active decision for 'existing_target'
    mock_semantic.list_decisions.return_value = ["dec_1.md"]
    
    # We need to mock the file loading for the active decision check
    mock_file_content = """---
kind: decision
context: {target: existing_target, status: active}
---
# Content"""
    
    with patch("builtins.open", MagicMock(side_effect=[MagicMock(read=lambda: mock_file_content), 
                                                      MagicMock(read=lambda: mock_file_content)])):
        from ledgermind.core.stores.semantic_store.loader import MemoryLoader
        with patch.object(MemoryLoader, "parse", return_value=({"kind": "decision", "context": {"target": "existing_target", "status": "active"}}, "body")):
            engine = ReflectionEngine(mock_episodic, mock_semantic)
            results = engine.run_cycle()
            
            # Should NOT create a success proposal because target is already active
            assert not any("Best Practice" in r for r in results)
