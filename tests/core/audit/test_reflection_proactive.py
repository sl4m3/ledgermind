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
    
    engine = ReflectionEngine(mock_episodic, mock_semantic, processor=mock_processor)
    
    mock_decision = MagicMock()
    mock_decision.should_persist = True
    mock_decision.metadata = {"file_id": "prop_123"}
    mock_processor.process_event.return_value = mock_decision
    
    results, _ = engine.run_cycle()
    
    assert "prop_123" in results
    
    args, kwargs = mock_processor.process_event.call_args
    assert kwargs["kind"] == "proposal"
    # V7.0 uses format "Hypothesis for {target}"
    assert "hypothesis for" in kwargs["content"].lower()
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

    engine = ReflectionEngine(mock_episodic, mock_semantic, processor=mock_processor)
    
    mock_decision = MagicMock()
    mock_decision.should_persist = True
    mock_decision.metadata = {"file_id": "prop_err_1"}
    mock_processor.process_event.return_value = mock_decision
    
    results, _ = engine.run_cycle()
    assert "prop_err_1" in results
    
    assert mock_processor.process_event.call_count >= 1
    
    processed_contents = [call.kwargs["content"] for call in mock_processor.process_event.call_args_list]
    assert any("hypothesis for" in c.lower() for c in processed_contents)

def test_reflection_allows_multiple_drafts_per_target():
    """Verify that reflection CAN create multiple drafts for the same target.
    
    V7.1: Idempotency check disabled to allow natural evolution via merging.
    Multiple draft proposals per target are expected and handled by merge engine.
    """
    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    mock_processor = MagicMock()

    now = datetime.now()
    mock_episodic.query.return_value = [
        {"id": i, "kind": "result", "content": "Success", "timestamp": now.isoformat(), "context": {"status": "active", "target": "existing_target", "success": True}}
        for i in range(6)
    ]

    # Even if there's an existing active decision for this target
    mock_semantic.meta.list_all.return_value = [
        {
            "fid": "stream_1",
            "kind": "decision",
            "status": "active",
            "target": "existing_target",
            "context_json": '{"decision_id": "stream_1", "title": "pattern", "rationale": "pattern of behavior", "phase": "emergent", "status": "active", "target": "existing_target", "vitality": "active", "evidence_event_ids": []}'
        }
    ]

    engine = ReflectionEngine(mock_episodic, mock_semantic, processor=mock_processor)
    results, _ = engine.run_cycle()

    # V7.1: Reflection CAN create new proposals even if target has active decisions
    # Merge engine will handle duplicates later
    assert mock_processor.process_event.call_count >= 1
    
    # Verify it created a hypothesis proposal
    processed_contents = [call.kwargs["content"] for call in mock_processor.process_event.call_args_list]
    assert any("hypothesis for" in c.lower() for c in processed_contents)
