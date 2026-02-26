import pytest
from pydantic import ValidationError
from ledgermind.server.contracts import (
    RecordDecisionRequest,
    SupersedeDecisionRequest,
    SearchDecisionsRequest,
    SyncGitHistoryRequest
)

# --- RecordDecisionRequest Tests ---

def test_record_decision_request_valid():
    data = {
        "title": "Valid Title",
        "target": "Valid Target",
        "rationale": "Rationale with enough length",
        "consequences": ["Rule 1"],
        "namespace": "custom"
    }
    request = RecordDecisionRequest(**data)
    assert request.title == data["title"]
    assert request.target == data["target"]
    assert request.rationale == data["rationale"]
    assert request.consequences == data["consequences"]
    assert request.namespace == data["namespace"]

def test_record_decision_request_defaults():
    data = {
        "title": "Valid Title",
        "target": "Valid Target",
        "rationale": "Rationale with enough length"
    }
    request = RecordDecisionRequest(**data)
    assert request.consequences == []
    assert request.namespace == "default"

def test_record_decision_request_invalid_title():
    with pytest.raises(ValidationError):
        RecordDecisionRequest(
            title="",
            target="target",
            rationale="rationale is long enough"
        )

def test_record_decision_request_invalid_target():
    with pytest.raises(ValidationError):
        RecordDecisionRequest(
            title="title",
            target="",
            rationale="rationale is long enough"
        )

def test_record_decision_request_invalid_rationale_short():
    # min_length=10
    with pytest.raises(ValidationError):
        RecordDecisionRequest(
            title="title",
            target="target",
            rationale="too short"
        )

# --- SupersedeDecisionRequest Tests ---

def test_supersede_decision_request_valid():
    data = {
        "title": "New Title",
        "target": "Target",
        "rationale": "Rationale that is at least fifteen chars",
        "old_decision_ids": ["d1", "d2"],
        "consequences": ["Effect 1"],
        "namespace": "custom"
    }
    request = SupersedeDecisionRequest(**data)
    assert request.title == data["title"]
    assert request.old_decision_ids == data["old_decision_ids"]

def test_supersede_decision_request_invalid_rationale_short():
    # min_length=15
    with pytest.raises(ValidationError):
        SupersedeDecisionRequest(
            title="title",
            target="target",
            rationale="too short",
            old_decision_ids=["d1"]
        )

def test_supersede_decision_request_invalid_old_ids_empty():
    # min_length=1
    with pytest.raises(ValidationError):
        SupersedeDecisionRequest(
            title="title",
            target="target",
            rationale="rationale that is long enough",
            old_decision_ids=[]
        )

# --- SearchDecisionsRequest Tests ---

def test_search_decisions_request_valid():
    data = {
        "query": "search query",
        "limit": 10,
        "offset": 5,
        "namespace": "custom",
        "mode": "audit"
    }
    request = SearchDecisionsRequest(**data)
    assert request.query == data["query"]
    assert request.limit == 10
    assert request.mode == "audit"

def test_search_decisions_request_defaults():
    request = SearchDecisionsRequest(query="test")
    assert request.limit == 5
    assert request.offset == 0
    assert request.namespace == "default"
    assert request.mode == "balanced"

def test_search_decisions_request_invalid_query_empty():
    with pytest.raises(ValidationError):
        SearchDecisionsRequest(query="")

def test_search_decisions_request_invalid_limit_low():
    # ge=1
    with pytest.raises(ValidationError):
        SearchDecisionsRequest(query="test", limit=0)

def test_search_decisions_request_invalid_limit_high():
    # le=50
    with pytest.raises(ValidationError):
        SearchDecisionsRequest(query="test", limit=51)

def test_search_decisions_request_invalid_offset_negative():
    # ge=0
    with pytest.raises(ValidationError):
        SearchDecisionsRequest(query="test", offset=-1)

def test_search_decisions_request_invalid_mode():
    with pytest.raises(ValidationError):
        SearchDecisionsRequest(query="test", mode="invalid")

# --- SyncGitHistoryRequest Tests ---

def test_sync_git_history_request_valid():
    request = SyncGitHistoryRequest(repo_path="/path/to/repo", limit=50)
    assert request.repo_path == "/path/to/repo"
    assert request.limit == 50

def test_sync_git_history_request_defaults():
    request = SyncGitHistoryRequest()
    assert request.repo_path == "."
    assert request.limit == 20

def test_sync_git_history_request_invalid_limit_low():
    # ge=1
    with pytest.raises(ValidationError):
        SyncGitHistoryRequest(limit=0)

def test_sync_git_history_request_invalid_limit_high():
    # le=100
    with pytest.raises(ValidationError):
        SyncGitHistoryRequest(limit=101)
