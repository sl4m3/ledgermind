import pytest
from unittest.mock import MagicMock
from ledgermind.core.reasoning.conflict import ConflictEngine
from ledgermind.core.core.schemas import MemoryEvent, KIND_DECISION, DecisionContent, ProposalContent

@pytest.fixture
def mock_meta_store():
    return MagicMock()

@pytest.fixture
def conflict_engine(mock_meta_store):
    return ConflictEngine(semantic_store_path="/tmp/semantic", meta_store=mock_meta_store)

def test_check_for_conflicts_detected(conflict_engine, mock_meta_store):
    """Test conflict detected when meta store returns an active file."""
    mock_meta_store.get_active_fid.return_value = "decision_123.md"

    event = MemoryEvent(
        source="agent",
        kind=KIND_DECISION,
        content="Some decision",
        context=DecisionContent(
            title="Test Decision",
            target="target1",
            rationale="Because I say so"
        )
    )

    result = conflict_engine.check_for_conflicts(event)

    assert result == "Conflict detected with: decision_123.md"
    mock_meta_store.get_active_fid.assert_called_with("target1", namespace="default")

def test_check_for_conflicts_no_conflict(conflict_engine, mock_meta_store):
    """Test no conflict when meta store returns None."""
    mock_meta_store.get_active_fid.return_value = None

    event = MemoryEvent(
        source="agent",
        kind=KIND_DECISION,
        content="Some decision",
        context=DecisionContent(
            title="Test Decision",
            target="target2",
            rationale="Because I say so"
        )
    )

    result = conflict_engine.check_for_conflicts(event)

    assert result is None
    mock_meta_store.get_active_fid.assert_called_with("target2", namespace="default")

def test_check_for_conflicts_not_decision(conflict_engine, mock_meta_store):
    """Test no conflict check for non-decision events."""
    event = MemoryEvent(
        source="agent",
        kind="proposal",
        content="Some proposal",
        context=ProposalContent(
            title="Test Proposal",
            target="target3",
            rationale="Maybe we should...",
            confidence=0.8
        )
    )

    result = conflict_engine.check_for_conflicts(event)

    assert result is None
    # Should not be called because kind is not KIND_DECISION
    mock_meta_store.get_active_fid.assert_not_called()

def test_check_for_conflicts_with_namespace(conflict_engine, mock_meta_store):
    """Test conflict check with specific namespace passed as argument."""
    mock_meta_store.get_active_fid.return_value = "decision_456.md"

    event = MemoryEvent(
        source="agent",
        kind=KIND_DECISION,
        content="Some decision",
        context=DecisionContent(
            title="Test Decision",
            target="target4",
            rationale="Because I say so",
            namespace="dev"
        )
    )

    # Passing explicit namespace should override event namespace
    result = conflict_engine.check_for_conflicts(event, namespace="prod")

    assert result == "Conflict detected with: decision_456.md"
    mock_meta_store.get_active_fid.assert_called_with("target4", namespace="prod")

def test_check_for_conflicts_event_namespace(conflict_engine, mock_meta_store):
    """Test conflict check using event namespace when no argument is provided."""
    mock_meta_store.get_active_fid.return_value = None

    event = MemoryEvent(
        source="agent",
        kind=KIND_DECISION,
        content="Some decision",
        context=DecisionContent(
            title="Test Decision",
            target="target5",
            rationale="Because I say so",
            namespace="custom_ns"
        )
    )

    conflict_engine.check_for_conflicts(event)

    mock_meta_store.get_active_fid.assert_called_with("target5", namespace="custom_ns")

def test_check_for_conflicts_no_meta_store():
    """Test RuntimeError when meta store is missing."""
    engine = ConflictEngine(semantic_store_path="/tmp/semantic", meta_store=None)

    event = MemoryEvent(
        source="agent",
        kind=KIND_DECISION,
        content="Some decision",
        context=DecisionContent(
            title="Test Decision",
            target="target6",
            rationale="Because I say so"
        )
    )

    with pytest.raises(RuntimeError, match="Metadata store required for performance"):
        engine.check_for_conflicts(event)
