import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from ledgermind.core.reasoning.reflection import ReflectionEngine, ReflectionPolicy

def test_reflection_proactive_success():
    """Verify that consistent successes lead to best practice proposals."""
    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    mock_processor = MagicMock()
    
    # Simulate 6 successes for the same target
    mock_episodic.query.return_value = [
        {"id": i, "kind": "result", "content": "Success", "timestamp": datetime.now(), "context": {"target": "auth_flow"}}
        for i in range(6)
    ]
    
    # Mock semantic meta instead of file reads
    mock_semantic.meta.list_active_targets.return_value = set()
    mock_semantic.meta.list_draft_proposals.return_value = []
    
    # Mock distillation to return nothing for this test to isolate success proposal
    with patch("ledgermind.core.reasoning.reflection.DistillationEngine") as mock_dist_class:
        mock_dist_class.return_value.distill_trajectories.return_value = []
        
        policy = ReflectionPolicy(success_threshold=5)
        engine = ReflectionEngine(mock_episodic, mock_semantic, policy=policy, processor=mock_processor)
        
        # Mock processor to return a decision with metadata
        mock_decision = MagicMock()
        mock_decision.should_persist = True
        mock_decision.metadata = {"file_id": "prop_123"}
        mock_processor.process_event.return_value = mock_decision
        
        results, _ = engine.run_cycle()
        
        # Check if a proposal was created for the success pattern
        assert "prop_123" in results
        
        # Verify the content of the proposal
        args, kwargs = mock_processor.process_event.call_args
        assert kwargs["kind"] == "proposal"
        assert "Best Practice" in kwargs["content"]
        assert kwargs["context"].target == "auth_flow"

def test_reflection_lower_error_threshold():
    """Verify that fewer errors now trigger a proposal in v4.1."""
    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    mock_processor = MagicMock()
    
    # Simulate 2 errors (new threshold is 2)
    mock_episodic.query.return_value = [
        {"id": 1, "kind": "error", "content": "Fail", "timestamp": datetime.now(), "context": {"target": "db_conn"}},
        {"id": 2, "kind": "error", "content": "Fail", "timestamp": datetime.now(), "context": {"target": "db_conn"}}
    ]
    
    mock_semantic.meta.list_active_targets.return_value = set()
    mock_semantic.meta.list_draft_proposals.return_value = []

    with patch("ledgermind.core.reasoning.reflection.DistillationEngine") as mock_dist_class:
        mock_dist_class.return_value.distill_trajectories.return_value = []

        policy = ReflectionPolicy(error_threshold=2)
        engine = ReflectionEngine(mock_episodic, mock_semantic, policy=policy, processor=mock_processor)
        
        mock_decision = MagicMock()
        mock_decision.should_persist = True
        mock_decision.metadata = {"file_id": "prop_err_1"}
        mock_processor.process_event.return_value = mock_decision
        
        results, _ = engine.run_cycle()
        assert "prop_err_1" in results
        
        # Check that competing hypotheses were processed
        assert mock_processor.process_event.call_count >= 2
        
        processed_contents = [call.kwargs["content"] for call in mock_processor.process_event.call_args_list]
        assert any("Structural flaw" in c for c in processed_contents)
        assert any("Environmental noise" in c for c in processed_contents)

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
            results, _ = engine.run_cycle()
            
            # Should NOT create a success proposal because target is already active
            assert not any("Best Practice" in r for r in results)
