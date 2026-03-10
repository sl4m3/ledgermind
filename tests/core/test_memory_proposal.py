import pytest
import os
import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import DecisionStream, KIND_PROPOSAL, BaseSemanticContent

@pytest.fixture
def memory(tmp_path):
    storage = tmp_path / "memory"
    os.makedirs(storage / "semantic")
    # Patch VectorStore class within the memory module to avoid GGUF errors
    with patch('ledgermind.core.api.memory.VectorStore'):
        mem = Memory(str(storage))
        yield mem

def test_accept_proposal_success(tmp_path):
    storage = tmp_path / "memory_accept"
    os.makedirs(storage / "semantic")
    
    with patch('ledgermind.core.api.memory.VectorStore'):
        memory = Memory(str(storage))
        
        # 1. Create a proposal
        proposal_id = "prop_1.md"
        memory.semantic.meta.upsert(
            fid=proposal_id, 
            target="test_target", 
            kind="proposal", 
            status="draft", 
            timestamp=datetime.now(),
            confidence=0.8
        )
        
        # Header must include rationale and confidence for loader
        with open(os.path.join(memory.semantic.repo_path, proposal_id), 'w') as f:
            f.write("---\nkind: proposal\ncontext:\n  target: test_target\n  title: Test Proposal\n  status: draft\n  rationale: Valid rationale for proposal\n  confidence: 0.8\n---\nProposal Body")

        # 2. Accept it
        res = memory.accept_proposal(proposal_id)
        
        # MemoryDecision uses should_persist, not status
        assert res.should_persist is True
        assert res.metadata["file_id"] is not None
        
        # 3. Verify status in meta
        meta = memory.semantic.meta.get_by_fid(proposal_id, unpack_context=True)
        assert meta["status"] == "accepted"
        assert meta["converted_to"] is not None
        
        # 4. Verify decision was created
        new_id = meta["converted_to"]
        assert os.path.exists(os.path.join(memory.semantic.repo_path, new_id))
        
        decision_data = memory.semantic.meta.get_by_fid(new_id, unpack_context=True)
        assert decision_data["status"] == "active"

def test_accept_proposal_supersede(tmp_path):
    storage = tmp_path / "memory_supersede"
    os.makedirs(storage / "semantic")
    
    with patch('ledgermind.core.api.memory.VectorStore'):
        memory = Memory(str(storage))
        
        # 1. Create an active decision to be superseded
        old_id = "decision_old.md"
        memory.semantic.meta.upsert(
            fid=old_id, 
            target="target_x", 
            kind="decision", 
            status="active", 
            timestamp=datetime.now()
        )
        with open(os.path.join(memory.semantic.repo_path, old_id), 'w') as f:
            f.write("---\nkind: decision\ncontext:\n  target: target_x\n  title: Old\n  status: active\n  rationale: Old rationale\n---\nOld")

        # 2. Create a proposal that supersedes old_id
        prop_id = "prop_2.md"
        memory.semantic.meta.upsert(
            fid=prop_id, 
            target="target_x", 
            kind="proposal", 
            status="draft", 
            timestamp=datetime.now(),
            confidence=0.9
        )
        with open(os.path.join(memory.semantic.repo_path, prop_id), 'w') as f:
            # Yaml header with explicit suggested_supersedes list
            f.write(f"---\nkind: proposal\ncontext:\n  target: target_x\n  title: New\n  status: draft\n  rationale: New rationale\n  confidence: 0.9\n  suggested_supersedes: [{old_id!r}]\n---\nNew")

        # 3. Accept it
        res = memory.accept_proposal(prop_id)
        assert res.should_persist is True
        
        # 4. Verify old is superseded
        old_meta = memory.semantic.meta.get_by_fid(old_id, unpack_context=True)
        assert old_meta["status"] == "superseded"
        assert old_meta["superseded_by"] is not None

def test_accept_proposal_not_found(tmp_path):
    storage = tmp_path / "memory_missing"
    os.makedirs(storage / "semantic")
    with patch('ledgermind.core.api.memory.VectorStore'):
        memory = Memory(str(storage))
        with pytest.raises(FileNotFoundError):
            memory.accept_proposal("nonexistent.md")

def test_accept_proposal_invalid_kind(tmp_path):
    storage = tmp_path / "memory_kind"
    os.makedirs(storage / "semantic")
    with patch('ledgermind.core.api.memory.VectorStore'):
        memory = Memory(str(storage))

        fid = "not_a_proposal.md"
        memory.semantic.meta.upsert(
            fid=fid,
            target="target",
            kind="decision",
            status="active",
            timestamp=datetime.now()
        )
        # Create a file with wrong kind (decision instead of proposal)
        with open(os.path.join(memory.semantic.repo_path, fid), 'w') as f:
            f.write("---\nkind: decision\ncontext:\n  target: target\n  title: Not a proposal\n  status: active\n  rationale: This is a decision\n---\nDecision")

        with pytest.raises(ValueError, match="not a proposal"):
            memory.accept_proposal(fid)
