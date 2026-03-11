import pytest
from datetime import datetime
from ledgermind.core.core.router import MemoryRouter
from ledgermind.core.core.schemas import MemoryEvent, MemoryDecision, ResolutionIntent, KIND_DECISION
from unittest.mock import MagicMock

@pytest.fixture
def mock_conflict_engine():
    return MagicMock()

@pytest.fixture
def mock_resolution_engine():
    return MagicMock()

@pytest.fixture
def router(mock_conflict_engine, mock_resolution_engine):
    return MemoryRouter(conflict_engine=mock_conflict_engine, resolution_engine=mock_resolution_engine)

def test_route_episodic_by_default(router):
    event = MemoryEvent(source="user", kind="prompt", content="Hello", timestamp=datetime.now())
    decision = router.route(event)
    assert decision.should_persist is True
    assert decision.store_type == "episodic"

def test_route_semantic_for_decision(router, mock_conflict_engine):
    mock_conflict_engine.get_conflict_files.return_value = []
    event = MemoryEvent(
        source="agent", 
        kind=KIND_DECISION, 
        content="Long Enough Title", 
        context={
            "target": "target_long", 
            "title": "Long Enough Title", 
            "rationale": "Rationale long enough for validation"
        }, 
        timestamp=datetime.now()
    )
    decision = router.route(event)
    assert decision.should_persist is True
    assert decision.store_type == "semantic"

def test_route_conflict_without_intent(router, mock_conflict_engine):
    mock_conflict_engine.get_conflict_files.return_value = ["file1.md"]
    event = MemoryEvent(
        source="agent", 
        kind=KIND_DECISION, 
        content="Long Enough Title", 
        context={
            "target": "target_long", 
            "title": "Long Enough Title", 
            "rationale": "Rationale long enough for validation"
        }, 
        timestamp=datetime.now()
    )
    decision = router.route(event)
    assert decision.should_persist is False
    assert "CONFLICT" in decision.reason
    assert "ResolutionIntent required" in decision.reason

def test_route_conflict_with_valid_intent(router, mock_conflict_engine, mock_resolution_engine):
    mock_conflict_engine.get_conflict_files.return_value = ["file1.md"]
    mock_resolution_engine.validate_intent.return_value = True
    
    event = MemoryEvent(
        source="agent", 
        kind=KIND_DECISION, 
        content="Long Enough Title", 
        context={
            "target": "target_long", 
            "title": "Long Enough Title", 
            "rationale": "Rationale long enough for validation"
        }, 
        timestamp=datetime.now()
    )
    intent = ResolutionIntent(resolution_type="supersede", rationale="Updating with long enough rationale", target_decision_ids=["file1.md"])
    
    decision = router.route(event, intent=intent)
    assert decision.should_persist is True
    assert decision.store_type == "semantic"

def test_route_conflict_with_invalid_intent(router, mock_conflict_engine, mock_resolution_engine):
    mock_conflict_engine.get_conflict_files.return_value = ["file1.md"]
    mock_resolution_engine.validate_intent.return_value = False
    
    event = MemoryEvent(
        source="agent", 
        kind=KIND_DECISION, 
        content="Long Enough Title", 
        context={
            "target": "target_long", 
            "title": "Long Enough Title", 
            "rationale": "Rationale long enough for validation"
        }, 
        timestamp=datetime.now()
    )
    intent = ResolutionIntent(resolution_type="supersede", rationale="Updating with long enough rationale", target_decision_ids=["wrong_file.md"])
    
    decision = router.route(event, intent=intent)
    assert decision.should_persist is False
    assert "CONFLICT" in decision.reason
    assert "ResolutionIntent is invalid" in decision.reason

def test_route_episodic_with_supersede_intent_remains_episodic(router):
    # This event is episodic (prompt)
    event = MemoryEvent(source="user", kind="prompt", content="Hello", timestamp=datetime.now())
    # But it has an intent to supersede
    intent = ResolutionIntent(resolution_type="supersede", rationale="Updating with long enough rationale", target_decision_ids=["file1.md"])
    
    decision = router.route(event, intent=intent)
    assert decision.should_persist is True
    # Should still be episodic because kind='prompt' is not in SEMANTIC_KINDS
    assert decision.store_type == "episodic"
