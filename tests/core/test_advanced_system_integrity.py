import pytest
import json
from unittest.mock import patch
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import KIND_PROPOSAL, MemoryEvent

@pytest.fixture
def memory(tmp_path):
    storage = str(tmp_path / "integrity_mem")
    return Memory(storage_path=storage)

def test_accept_proposal_rollback_preserves_draft_status(memory):
    """Ensures that if accept_proposal fails, the proposal remains 'draft' on disk."""
    # 1. Create a proposal
    proposal_content = {
        "title": "New Pattern",
        "target": "Network-Architecture",
        "rationale": "High-level rationale for this proposal.",
        "status": "draft",
        "confidence": 0.9
    }
    proposal_id = memory.semantic.save(MemoryEvent(
        source="agent",
        kind=KIND_PROPOSAL,
        content="Proposal summary",
        context=proposal_content
    ))

    # 2. Force failure during conversion using patch
    with patch.object(memory._decision_command, 'supersede_decision', side_effect=RuntimeError("Simulated failure")):
        with pytest.raises(RuntimeError, match="Simulated failure"):
            memory.accept_proposal(proposal_id)

    # 3. Verify status is still draft in MetaStore
    meta = memory.semantic.meta.get_by_fid(proposal_id)
    assert meta['status'] == "draft"
    
    # 4. Verify context_json still has original content
    ctx = json.loads(meta['context_json'])
    assert ctx['title'] == "New Pattern"
