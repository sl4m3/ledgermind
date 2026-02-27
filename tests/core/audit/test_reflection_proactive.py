import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from ledgermind.core.reasoning.reflection import ReflectionEngine, ReflectionPolicy

def test_reflection_proactive_success():
    """Verify that consistent successes lead to a behavioral pattern stream."""
    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    mock_processor = MagicMock()
    
    now = datetime.now()
    # Simulate 6 successes for the same target
    mock_episodic.query.return_value = [
        {"id": i, "kind": "result", "content": "Success", "timestamp": now.isoformat(), "context": {"target": "auth_flow", "success": True}}
        for i in range(6)
    ]
    
    mock_semantic.meta.list_all.return_value = []
    
    with patch("ledgermind.core.reasoning.reflection.DistillationEngine") as mock_dist_class:
        engine = ReflectionEngine(mock_episodic, mock_semantic, processor=mock_processor)
        
        mock_decision = MagicMock()
        mock_decision.should_persist = True
        mock_decision.metadata = {"file_id": "prop_123"}
        mock_processor.process_event.return_value = mock_decision
        
        results, _ = engine.run_cycle()
        
        assert "prop_123" in results
        
        args, kwargs = mock_processor.process_event.call_args
        assert kwargs["kind"] == "proposal"
        assert "Behavioral pattern" in kwargs["content"]
        assert kwargs["context"].target == "auth_flow"

def test_reflection_lower_error_threshold():
    """Verify that errors also trigger a stream pattern."""
    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    mock_processor = MagicMock()
    
    now = datetime.now()
    mock_episodic.query.return_value = [
        {"id": 1, "kind": "error", "content": "Fail", "timestamp": now.isoformat(), "context": {"target": "db_conn"}},
        {"id": 2, "kind": "error", "content": "Fail", "timestamp": now.isoformat(), "context": {"target": "db_conn"}}
    ]
    
    mock_semantic.meta.list_all.return_value = []

    with patch("ledgermind.core.reasoning.reflection.DistillationEngine") as mock_dist_class:
        engine = ReflectionEngine(mock_episodic, mock_semantic, processor=mock_processor)
        
        mock_decision = MagicMock()
        mock_decision.should_persist = True
        mock_decision.metadata = {"file_id": "prop_err_1"}
        mock_processor.process_event.return_value = mock_decision
        
        results, _ = engine.run_cycle()
        assert "prop_err_1" in results
        
        assert mock_processor.process_event.call_count >= 1
        
        processed_contents = [call.kwargs["content"] for call in mock_processor.process_event.call_args_list]
        assert any("Behavioral pattern" in c for c in processed_contents)

def test_reflection_skips_active_targets():
    """Verify that it updates existing stream instead of creating a new one."""
    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    mock_processor = MagicMock()
    
    now = datetime.now()
    mock_episodic.query.return_value = [
        {"id": i, "kind": "result", "content": "Success", "timestamp": now.isoformat(), "context": {"target": "existing_target"}}
        for i in range(6)
    ]
    
    # Mock an existing stream for 'existing_target'
    mock_semantic.meta.list_all.return_value = [
        {
            "fid": "stream_1",
            "kind": "decision",
                            "context_json": '{"decision_id": "stream_1", "title": "pattern", "rationale": "pattern of behavior", "phase": "emergent", "target": "existing_target", "vitality": "active", "evidence_event_ids": []}'        }
    ]
    
    with patch("ledgermind.core.reasoning.reflection.DistillationEngine") as mock_dist_class:
        engine = ReflectionEngine(mock_episodic, mock_semantic, processor=mock_processor)
        results, _ = engine.run_cycle()
    
        # Should NOT call process_event (create), but should call update_decision
        assert mock_processor.process_event.call_count == 0
    assert mock_processor.update_decision.call_count >= 1
    
    args, kwargs = mock_processor.update_decision.call_args
    assert args[0] == "stream_1"
