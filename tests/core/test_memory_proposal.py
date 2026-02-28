import pytest
import os
import yaml
import json
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import KIND_PROPOSAL, KIND_DECISION
from ledgermind.core.stores.semantic_store.loader import MemoryLoader

@pytest.fixture
def memory_instance(tmp_path):
    storage_path = str(tmp_path / "memory")
    os.makedirs(storage_path, exist_ok=True)

    # Initialize Memory with minimal config
    # We use a mocked vector model or just allow it to fail/warn if model not found
    # But to avoid download/load time, maybe we can mock vector store or just ignore errors
    # Memory catches vector errors usually.
    # Set vector_workers=0 to avoid multiprocessing issues in tests
    mem = Memory(vector_model="v5-small-text-matching-Q4_K_M.gguf", storage_path=storage_path, vector_workers=0)

    yield mem
    mem.close()

def create_proposal_file(memory, title, target, rationale, supersedes=None, status="draft"):
    content = {
        "kind": KIND_PROPOSAL,
        "title": title,
        "content": rationale,
        "context": {
            "title": title,
            "target": target,
            "rationale": rationale,
            "status": status,
            "suggested_supersedes": supersedes or [],
            "suggested_consequences": [],
            "evidence_event_ids": []
        }
    }

    # Use MemoryLoader.stringify to create file content
    file_content = MemoryLoader.stringify(content, body=rationale)

    # Manually save to semantic repo
    file_id = f"proposal_{title.replace(' ', '_').lower()}.md"
    file_path = os.path.join(memory.semantic.repo_path, file_id)

    with open(file_path, "w") as f:
        f.write(file_content)

    return file_id

def test_accept_proposal_success(memory_instance):
    prop_id = create_proposal_file(
        memory_instance,
        "Test Proposal",
        "Test Target",
        "This is a test rationale"
    )

    decision = memory_instance.accept_proposal(prop_id)

    assert decision.should_persist is True
    assert decision.store_type == "semantic"

    # check proposal status updated
    with open(os.path.join(memory_instance.semantic.repo_path, prop_id), "r") as f:
        data, _ = MemoryLoader.parse(f.read())
        assert data["context"]["status"] == "accepted"
        assert "converted_to" in data["context"]

    # check new decision exists
    new_id = decision.metadata["file_id"]
    assert os.path.exists(os.path.join(memory_instance.semantic.repo_path, new_id))

    # verify content
    meta = memory_instance.semantic.meta.get_by_fid(new_id)
    assert meta["title"] == "Test Proposal"
    assert meta["target"] == "Test Target"
    assert meta["kind"] == KIND_DECISION
    assert meta["status"] == "active"

def test_accept_proposal_supersede(memory_instance):
    # 1. Create an initial decision
    init_decision = memory_instance.record_decision(
        title="Initial Decision",
        target="Supersede Target",
        rationale="Initial Rationale"
    )
    init_id = init_decision.metadata["file_id"]

    # 2. Create a proposal that supersedes it
    prop_id = create_proposal_file(
        memory_instance,
        "Superseding Proposal",
        "Supersede Target",
        "Better Rationale",
        supersedes=[init_id]
    )

    # 3. Accept proposal
    decision = memory_instance.accept_proposal(prop_id)

    # 4. Verify superseding logic
    new_id = decision.metadata["file_id"]
    assert new_id != init_id

    # Check old decision is superseded
    old_meta = memory_instance.semantic.meta.get_by_fid(init_id)
    assert old_meta["status"] == "superseded"
    assert old_meta["superseded_by"] == new_id

    # Check new decision is active
    new_meta = memory_instance.semantic.meta.get_by_fid(new_id)
    assert new_meta["status"] == "active"

def test_accept_proposal_not_found(memory_instance):
    with pytest.raises(FileNotFoundError):
        memory_instance.accept_proposal("non_existent_proposal.md")

def test_accept_proposal_invalid_kind(memory_instance):
    # Create a decision file manually and try to accept it
    file_id = "fake_proposal.md"
    content = {
        "kind": KIND_DECISION, # Not a proposal
        "title": "Fake",
        "context": {"status": "draft"}
    }
    file_path = os.path.join(memory_instance.semantic.repo_path, file_id)
    with open(file_path, "w") as f:
        f.write(MemoryLoader.stringify(content))

    with pytest.raises(ValueError, match="is not a proposal"):
        memory_instance.accept_proposal(file_id)

def test_accept_proposal_invalid_status(memory_instance):
    prop_id = create_proposal_file(
        memory_instance,
        "Already Accepted",
        "Target",
        "Rationale",
        status="accepted"
    )

    with pytest.raises(ValueError, match="already accepted"):
        memory_instance.accept_proposal(prop_id)
