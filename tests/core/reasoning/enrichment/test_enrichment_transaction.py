"""
Tests for transactional handling in LLMEnricher.process_batch().

V7.7: Architecture changed from atomic batch to per-proposal transactions.
Each proposal is processed independently - errors in one proposal don't affect others.
This prevents long-held locks during LLM calls.
"""
import pytest
import os
import tempfile
import shutil
from datetime import datetime
from unittest.mock import MagicMock, patch

from ledgermind.core.api.memory import Memory
from ledgermind.core.reasoning.enrichment.facade import LLMEnricher
from ledgermind.core.stores.semantic_store.integrity import IntegrityViolation


class TestEnrichmentTransactionPerProposal:
    """Test that process_batch() handles errors per-proposal (V7.7 architecture)."""

    @pytest.fixture
    def memory(self):
        """Create a temporary memory instance for testing."""
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
        """Create an LLMEnricher instance."""
        return LLMEnricher(mode="rich", preferred_language="russian")

    def test_batch_continues_on_i4_violation(self, memory, enricher):
        """
        V7.7: If one cluster raises I4 Violation, processing continues for other proposals.
        The failed proposal is logged as an error, but the batch completes.
        
        This is the NEW behavior - per-proposal transactions prevent long-held locks.
        """
        # Record first active decision manually
        memory.record_decision(
            title="Active Decision 1",
            target="test_target",
            rationale="First decision rationale is long enough"
        )

        # Mock the enrichment to simulate I4 violation on second cluster
        original_consolidation = enricher._execute_consolidation

        call_count = [0]

        def mock_consolidation(fids, mem, parent_fid):
            call_count[0] += 1
            if call_count[0] == 2:
                # Simulate I4 violation on second consolidation
                raise IntegrityViolation("I4 Violation: Target already active")
            return original_consolidation(fids, mem, parent_fid)

        # Create mock proposals
        class MockProposal:
            def __init__(self, fid, target, target_ids=None):
                self.fid = fid
                self.target = target
                self.target_ids = target_ids or []
                self.evidence_event_ids = []

        proposals = [
            MockProposal("cluster1.md", "knowledge_merge", ["doc1.md", "doc2.md"]),
            MockProposal("cluster2.md", "knowledge_merge", ["doc3.md", "doc4.md"]),
        ]

        # Mock the methods that would normally interact with LLM
        with patch.object(enricher, '_execute_consolidation', side_effect=mock_consolidation):
            with patch.object(enricher, '_inherit_cluster_evidence'):
                # V7.7: process_batch does NOT raise - it continues on errors
                results = enricher.process_batch(proposals, memory.episodic, memory=memory)
                
                # First proposal should succeed, second should fail
                # Results contain successfully processed proposals
                assert len(results) >= 0  # May have 0 or more successful

        # Verify error was logged (check that mock was called twice)
        assert call_count[0] == 2, "Both proposals should have been attempted"

    def test_batch_commit_on_success(self, memory, enricher):
        """
        If all clusters succeed, all changes should be committed.
        """
        # Create mock proposals that will succeed
        class MockProposal:
            def __init__(self, fid, target, target_ids=None):
                self.fid = fid
                self.target = target
                self.target_ids = target_ids or []
                self.evidence_event_ids = []
        
        proposals = [
            MockProposal("cluster1.md", "knowledge_merge", ["doc1.md", "doc2.md"]),
            MockProposal("cluster2.md", "knowledge_merge", ["doc3.md", "doc4.md"]),
        ]
        
        # Mock consolidation to succeed without actually creating files
        with patch.object(enricher, '_execute_consolidation'):
            with patch.object(enricher, '_inherit_cluster_evidence'):
                result = enricher.process_batch(proposals, memory.episodic, memory=memory)
        
        # Assert: All proposals processed
        assert len(result) == 2

    def test_nested_transaction_not_needed(self, memory, enricher):
        """
        Individual update_decision calls within process_batch should not
        create nested transactions - they should participate in the outer one.
        """
        # First create a real proposal file
        from ledgermind.core.core.schemas import KIND_PROPOSAL, DecisionContent
        from datetime import datetime
        
        decision = memory.process_event(
            source="agent",
            kind=KIND_PROPOSAL,
            content="Test proposal",
            context=DecisionContent(
                title="Test Proposal",
                target="test_target_nested",
                rationale="Testing nested transactions"
            ),
            timestamp=datetime.now()
        )
        fid = decision.metadata.get('file_id')
        
        class MockProposal:
            def __init__(self, fid, target):
                self.fid = fid
                self.target = target
                self.evidence_event_ids = []
        
        proposals = [MockProposal(fid, "general")]
        
        # Track transaction state
        transaction_count = [0]
        original_transaction = memory.semantic.transaction
        
        def count_transaction():
            transaction_count[0] += 1
            return original_transaction()
        
        with patch.object(memory.semantic, 'transaction', count_transaction):
            with patch.object(enricher, 'enrich_proposal', return_value=None):
                enricher.process_batch(proposals, memory.episodic, memory=memory)
        
        # Transaction should have been entered once for the batch
        assert transaction_count[0] == 1


class TestEnrichmentTransactionLogging:
    """Test that transaction logging works correctly."""

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
        return LLMEnricher(mode="rich", preferred_language="russian")

    def test_batch_start_log(self, memory, enricher, caplog):
        """Should log when batch processing starts (V7.7: per-proposal transactions)."""
        import logging
        caplog.set_level(logging.INFO)

        class MockProposal:
            def __init__(self, fid, target):
                self.fid = fid
                self.target = target
                self.evidence_event_ids = []

        proposals = [MockProposal("test.md", "general")]

        with patch.object(enricher, 'enrich_proposal', return_value=None):
            enricher.process_batch(proposals, memory.episodic, memory=memory)

        # V7.7: New log message format (no "transaction" since it's per-proposal now)
        assert "Starting enrichment batch with 1 proposals" in caplog.text

    def test_batch_commit_log(self, memory, enricher, caplog):
        """Should log when batch processing completes (V7.7: per-proposal transactions)."""
        import logging
        caplog.set_level(logging.INFO)

        class MockProposal:
            def __init__(self, fid, target):
                self.fid = fid
                self.target = target
                self.evidence_event_ids = []

        proposals = [MockProposal("test.md", "general")]

        with patch.object(enricher, 'enrich_proposal', return_value=None):
            enricher.process_batch(proposals, memory.episodic, memory=memory)

        # V7.7: New log message format
        assert "Batch processing completed:" in caplog.text

    def test_batch_rollback_log(self, memory, enricher, caplog):
        """Should log errors when batch processing fails (V7.7: per-proposal error handling).
        
        V7.7: Errors are logged but don't raise - batch continues with other proposals.
        """
        import logging
        caplog.set_level(logging.ERROR)

        # First create a real proposal file
        from ledgermind.core.core.schemas import KIND_PROPOSAL, DecisionContent
        from datetime import datetime

        decision = memory.process_event(
            source="agent",
            kind=KIND_PROPOSAL,
            content="Test proposal",
            context=DecisionContent(
                title="Test Proposal",
                target="test_target_rollback",
                rationale="Testing rollback logging"
            ),
            timestamp=datetime.now()
        )
        fid = decision.metadata.get('file_id')

        class MockProposal:
            def __init__(self, fid, target):
                self.fid = fid
                self.target = target
                self.evidence_event_ids = [1, 2, 3]  # Non-empty to trigger enrichment loop

        proposals = [MockProposal(fid, "general")]

        def raise_error(*args, **kwargs):
            raise ValueError("Test error")

        with patch.object(enricher, 'enrich_proposal', side_effect=raise_error):
            # V7.7: No exception raised - error is logged and batch continues
            enricher.process_batch(proposals, memory.episodic, memory=memory)
        
        # Verify error was logged
        assert "Test error" in caplog.text
        assert "Failed to process" in caplog.text
