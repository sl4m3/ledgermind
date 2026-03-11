import pytest
import os
import json
from datetime import datetime
from ledgermind.core.api.memory import Memory

@pytest.fixture
def memory(tmp_path):
    storage = str(tmp_path / "memory_proposal")
    os.makedirs(os.path.join(storage, "semantic"), exist_ok=True)
    return Memory(storage_path=storage)

def test_accept_proposal_success(memory):
    """Test successful conversion of proposal to active decision."""
    proposal_id = "prop_1.md"
    title = "Test Proposal"
    target = "test_target"
    content = "Proposal summary"
    ctx = {
        "title": title,
        "target": target,
        "rationale": "Valid rationale for proposal",
        "status": "draft",
        "confidence": 0.8
    }
    
    # 1. Create a proposal via upsert (V7.0)
    memory.semantic.meta.upsert(
        fid=proposal_id, 
        target=target, 
        title=title,
        kind="proposal", 
        status="draft", 
        timestamp=datetime.now(),
        content=content,
        context_json=json.dumps(ctx)
    )
    
    # Header must match for loader.parse
    with open(os.path.join(memory.semantic.repo_path, proposal_id), 'w') as f:
        f.write(f"---\nkind: proposal\ncontext:\n  target: {target}\n  title: {title}\n  status: draft\n  rationale: Valid rationale\n  confidence: 0.8\n---\n{content}")

    # 2. Accept it
    res = memory.accept_proposal(proposal_id)
    
    assert res.should_persist is True
    assert res.metadata["file_id"] is not None
    
    # 3. Verify status in meta
    meta = memory.semantic.meta.get_by_fid(proposal_id)
    assert meta["status"] == "accepted"
    
    # 4. Verify decision was created
    new_id = meta["converted_to"]
    assert new_id is not None
    assert os.path.exists(os.path.join(memory.semantic.repo_path, new_id))
    
    decision_data = memory.semantic.meta.get_by_fid(new_id)
    assert decision_data["status"] == "active"

def test_accept_proposal_supersede(memory):
    """Test proposal acceptance with superseding existing decision."""
    old_id = "decision_old.md"
    target = "target_x"
    
    # 1. Create an active decision
    memory.semantic.meta.upsert(
        fid=old_id, target=target, title="Old", status="active", kind="decision",
        timestamp=datetime.now(), content="Old", context_json=json.dumps({"title": "Old", "target": target, "rationale": "Old rationale"})
    )
    with open(os.path.join(memory.semantic.repo_path, old_id), 'w') as f:
        f.write("---\nkind: decision\ncontext:\n  target: target_x\n  title: Old\n  status: active\n  rationale: Old rationale\n---\nOld")

    # 2. Create a proposal that supersedes old_id
    prop_id = "prop_2.md"
    ctx = {
        "title": "New", "target": target, "status": "draft", "rationale": "New rationale",
        "suggested_supersedes": [old_id]
    }
    memory.semantic.meta.upsert(
        fid=prop_id, target=target, title="New", kind="proposal", status="draft",
        timestamp=datetime.now(), content="New", context_json=json.dumps(ctx)
    )
    with open(os.path.join(memory.semantic.repo_path, prop_id), 'w') as f:
        f.write(f"---\nkind: proposal\ncontext:\n  target: {target}\n  title: New\n  status: draft\n  rationale: New rationale\n  suggested_supersedes: [{old_id!r}]\n---\nNew")

    # 3. Accept it
    res = memory.accept_proposal(prop_id)
    assert res.should_persist is True
    
    # 4. Verify old is superseded
    old_meta = memory.semantic.meta.get_by_fid(old_id)
    assert old_meta["status"] == "superseded"
    assert old_meta["superseded_by"] is not None

def test_accept_proposal_not_found(memory):
    with pytest.raises(FileNotFoundError):
        memory.accept_proposal("nonexistent.md")

def test_accept_proposal_invalid_kind(memory):
    fid = "not_a_proposal.md"
    memory.semantic.meta.upsert(
        fid=fid, target="target", title="Not a proposal", status="active", kind="decision",
        timestamp=datetime.now(), content="Not a proposal", context_json="{}"
    )
    with open(os.path.join(memory.semantic.repo_path, fid), 'w') as f:
        f.write("---\nkind: decision\ncontext:\n  target: target\n  title: Not a proposal\n  status: active\n  rationale: This is a decision\n---\nDecision")

    with pytest.raises(ValueError, match="(?i)not a proposal"):
        memory.accept_proposal(fid)
