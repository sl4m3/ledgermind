from datetime import datetime
import pytest
from pydantic import ValidationError
from ledgermind.core.core.schemas import (
    MemoryEvent,
    BaseSemanticContent,
    DecisionStream,
    KIND_DECISION,
    KIND_PROPOSAL
)

def test_memory_event_valid_minimal():
    """Test creating a valid MemoryEvent with minimal required fields."""
    event = MemoryEvent(
        source="system",
        kind="call",
        content="Function called",
    )
    assert event.schema_version == 1
    assert isinstance(event.timestamp, datetime)
    assert event.source == "system"
    assert event.kind == "call"
    assert event.content == "Function called"
    assert event.context == {}

def test_memory_event_empty_content():
    """Test that ValueError is raised when content is empty."""
    with pytest.raises(ValidationError) as excinfo:
        MemoryEvent(
            source="system",
            kind="call",
            content="",
        )
    # Pydantic V2 StringConstraints(min_length=1) triggers first
    assert "String should have at least 1 character" in str(excinfo.value) or "Content cannot be empty" in str(excinfo.value)

def test_memory_event_invalid_kind():
    """Test that ValidationError is raised when kind is invalid."""
    with pytest.raises(ValidationError) as excinfo:
        MemoryEvent(
            source="system",
            kind="invalid_kind",
            content="Some content",
        )
    assert "Input should be" in str(excinfo.value) # Pydantic error message for literal

def test_memory_event_context_validation_decision():
    """Test that context is converted to DecisionContent when kind is decision."""
    decision_data = {
        "title": "Test Decision",
        "target": "target-system",
        "rationale": "Because it is better",
        "namespace": "default",
    }
    event = MemoryEvent(
        source="agent",
        kind=KIND_DECISION,
        content="Made a decision",
        context=decision_data
    )
    assert isinstance(event.context, DecisionStream)
    assert event.context.title == "Test Decision"
    assert event.context.target == "target-system"

def test_memory_event_context_validation_proposal():
    """Test that context is converted to ProposalContent when kind is proposal."""
    proposal_data = {
        "title": "Test Proposal",
        "target": "target-system",
        "rationale": "Hypothesis based on data",
        "namespace": "default",
        "confidence": 0.8,
    }
    event = MemoryEvent(
        source="agent",
        kind=KIND_PROPOSAL,
        content="Proposed a hypothesis",
        context=proposal_data
    )
    assert isinstance(event.context, DecisionStream)
    assert event.context.title == "Test Proposal"
    assert event.context.confidence == 0.8

def test_memory_event_context_validation_invalid_decision():
    """Test that context remains dict when invalid for decision."""
    invalid_data = {
        "title": "", # Invalid: empty
        "target": "target-system",
        "rationale": "Because", # Invalid: too short
    }
    event = MemoryEvent(
        source="agent",
        kind=KIND_DECISION,
        content="Made a decision",
        context=invalid_data
    )
    # Silently falls back to dict
    assert isinstance(event.context, dict)
    assert event.context == invalid_data

def test_memory_event_context_validation_invalid_proposal():
    """Test that context remains dict when invalid for proposal."""
    invalid_data = {
        "title": "Valid Title",
        "target": "valid-target",
        "rationale": "Short", # Too short rationale (<10)
        "confidence": 1.5, # Invalid: > 1.0
    }
    event = MemoryEvent(
        source="agent",
        kind=KIND_PROPOSAL,
        content="Proposed a hypothesis",
        context=invalid_data
    )
    # Silently falls back to dict
    assert isinstance(event.context, dict)
    assert event.context == invalid_data

def test_memory_event_context_non_semantic():
    """Test that context remains a dict when kind is non-semantic."""
    context_data = {"some_key": "some_value"}
    event = MemoryEvent(
        source="system",
        kind="call", # non-semantic kind
        content="Function called",
        context=context_data
    )
    assert isinstance(event.context, dict)
    assert event.context == context_data

def test_decision_content_valid():
    """Test creating a valid DecisionContent."""
    decision = BaseSemanticContent(
        title="Valid Decision",
        target="valid-target",
        rationale="Valid rationale with enough length",
        namespace="core"
    )
    assert decision.title == "Valid Decision"
    assert decision.status == "draft"

def test_decision_content_empty_fields():
    """Test that empty strings for required fields in DecisionContent raise ValueError."""
    with pytest.raises(ValidationError) as excinfo:
        BaseSemanticContent(
            title="",
            target="valid-target",
            rationale="Valid rationale"
        )
    assert "String should have at least 1 character" in str(excinfo.value) or "Field cannot be empty" in str(excinfo.value)

def test_proposal_content_valid():
    """Test creating a valid ProposalContent."""
    proposal = DecisionStream(
        title="Valid Proposal",
        target="valid-target",
        rationale="Valid rationale with enough length",
        confidence=0.5
    )
    assert proposal.title == "Valid Proposal"
    assert proposal.status == "draft"
    assert proposal.confidence == 0.5

def test_proposal_content_invalid_confidence():
    """Test that invalid confidence values raise ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        DecisionStream(
            title="Valid Proposal",
            target="valid-target",
            rationale="Valid rationale with enough length",
            confidence=1.5 # Invalid
        )
    # Pydantic error message might vary slightly (1 or 1.0)
    assert "Input should be less than or equal to 1" in str(excinfo.value)

    with pytest.raises(ValidationError) as excinfo:
        DecisionStream(
            title="Valid Proposal",
            target="valid-target",
            rationale="Valid rationale with enough length",
            confidence=-0.1 # Invalid
        )
    assert "Input should be greater than or equal to 0" in str(excinfo.value)

def test_proposal_content_invalid_rationale_length():
    """Test that short rationale raises ValidationError."""
    with pytest.raises(ValidationError) as excinfo:
        DecisionStream(
            title="Valid Proposal",
            target="valid-target",
            rationale="Short", # < 10 chars
            confidence=0.5
        )
    assert "String should have at least 10 characters" in str(excinfo.value)
