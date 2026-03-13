"""
Tests for evidence inheritance during consolidation.
"""
import pytest
import tempfile
import shutil
from datetime import datetime
from unittest.mock import patch

from ledgermind.core.api.memory import Memory
from ledgermind.core.reasoning.enrichment.facade import LLMEnricher
from ledgermind.core.core.schemas import KIND_PROPOSAL, DecisionContent


class TestEvidenceInheritance:
    """Test that total_evidence_count is properly inherited during consolidation."""

    @pytest.fixture
    def memory(self):
        storage_path = tempfile.mkdtemp()
        memory = Memory(storage_path=storage_path)
        yield memory
        memory.close()
        try:
            shutil.rmtree(storage_path)
        except Exception:
            pass

    @pytest.fixture
    def enricher(self):
        return LLMEnricher(mode="rich", enrichment_language="russian")

    def test_consolidation_inherits_total_evidence_count(self, memory, enricher):
        """
        When consolidating multiple proposals, total_evidence_count 
        should be summed from all source proposals.
        
        Note: Decisions don't inherit evidence_event_ids directly - they are
        higher-level abstractions. Only the count is preserved for history.
        """
        # Create 3 proposals with different evidence counts
        def create_proposal(title, target, total_count):
            decision = memory.process_event(
                source="agent",
                kind=KIND_PROPOSAL,
                content=title,
                context=DecisionContent(
                    title=title,
                    target=target,
                    rationale="Test rationale",
                    total_evidence_count=total_count
                ),
                timestamp=datetime.now()
            )
            return decision.metadata.get('file_id')

        fid1 = create_proposal("Proposal 1", "test_consolidation", 10)
        fid2 = create_proposal("Proposal 2", "test_consolidation", 20)
        fid3 = create_proposal("Proposal 3", "test_consolidation", 30)

        # Mock LLM response for consolidation
        mock_response = '''```json
{
    "title": "Consolidated Decision",
    "target": "test_consolidation",
    "rationale": "Combined rationale",
    "keywords": ["test"],
    "strengths": ["strength1"],
    "objections": ["objection1"],
    "consequences": ["consequence1"]
}
```'''

        # Mock the LLM client
        with patch.object(enricher, '_get_client') as mock_client_getter:
            mock_client = mock_client_getter.return_value
            mock_client.call.return_value = mock_response
            
            # Mock _inherit_cluster_evidence to avoid episodic store complexity
            with patch.object(enricher, '_inherit_cluster_evidence'):
                # Execute consolidation
                enricher._execute_consolidation([fid1, fid2, fid3], memory, "test_parent.md")

        # Check that the new decision has summed evidence count
        all_meta = memory.semantic.meta.list_all()
        consolidated = [
            m for m in all_meta 
            if m.get('kind') == 'decision' and m.get('target') == 'test_consolidation'
        ]
        
        assert len(consolidated) == 1
        new_decision = consolidated[0]
        
        # Should have inherited 10 + 20 + 30 = 60
        ctx = memory.semantic.meta._conn.execute(
            'SELECT context_json FROM semantic_meta WHERE fid = ?', 
            (new_decision['fid'],)
        ).fetchone()
        
        import json
        if ctx and ctx[0]:
            ctx_data = json.loads(ctx[0])
            assert ctx_data.get('total_evidence_count', 0) == 60
            # Decisions should NOT have evidence_event_ids
            assert ctx_data.get('evidence_event_ids', []) == []

    def test_consolidation_with_zero_evidence(self, memory, enricher):
        """
        Consolidation should work correctly even if all sources have 0 evidence.
        """
        def create_proposal(title, target):
            decision = memory.process_event(
                source="agent",
                kind=KIND_PROPOSAL,
                content=title,
                context=DecisionContent(
                    title=title,
                    target=target,
                    rationale="Test rationale"
                ),
                timestamp=datetime.now()
            )
            return decision.metadata.get('file_id')

        fid1 = create_proposal("Proposal 1", "test_zero")
        fid2 = create_proposal("Proposal 2", "test_zero")

        mock_response = '''```json
{
    "title": "Consolidated Zero",
    "target": "test_zero",
    "rationale": "This is a combined rationale that is long enough for validation",
    "keywords": []
}
```'''

        with patch.object(enricher, '_get_client') as mock_client_getter:
            mock_client = mock_client_getter.return_value
            mock_client.call.return_value = mock_response

            with patch.object(enricher, '_inherit_cluster_evidence'):
                enricher._execute_consolidation([fid1, fid2], memory, "test_parent.md")

        # Should complete without error
        all_meta = memory.semantic.meta.list_all()
        consolidated = [
            m for m in all_meta
            if m.get('kind') == 'decision' and m.get('target') == 'test_zero'
        ]

        assert len(consolidated) == 1
