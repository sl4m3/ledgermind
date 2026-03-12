"""
Tests for list_active_conflicts method to ensure draft records are not treated as conflicts.

This addresses the bug where draft proposals were incorrectly flagged as I4 violations
when creating new active decisions with the same target.
"""
import pytest
import sqlite3
import os
import tempfile
from datetime import datetime
from ledgermind.core.stores.semantic_store.meta import SemanticMetaStore
from ledgermind.core.stores.semantic import SemanticStore


class TestSemanticMetaStoreListActiveConflicts:
    """Test list_active_conflicts in SemanticMetaStore."""

    @pytest.fixture
    def meta_store(self):
        """Create a temporary meta store for testing."""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store = SemanticMetaStore(db_path)
        yield store
        store.close()
        try:
            os.unlink(db_path)
            # Clean up WAL files if they exist
            for ext in ["-wal", "-shm"]:
                if os.path.exists(db_path + ext):
                    os.unlink(db_path + ext)
        except Exception:
            pass

    def test_only_active_records_returned(self, meta_store):
        """Only 'active' status records should be returned as conflicts."""
        # Insert test data
        meta_store.upsert(
            fid="active_decision.md",
            target="docs",
            title="Active Decision",
            status="active",
            kind="decision",
            timestamp=datetime.now(),
            content="Active content",
            context_json='{}'
        )
        meta_store.upsert(
            fid="draft_proposal.md",
            target="docs",
            title="Draft Proposal",
            status="draft",
            kind="proposal",
            timestamp=datetime.now(),
            content="Draft content",
            context_json='{}'
        )
        meta_store.upsert(
            fid="superseded_decision.md",
            target="docs",
            title="Superseded Decision",
            status="superseded",
            kind="decision",
            timestamp=datetime.now(),
            content="Superseded content",
            context_json='{}'
        )
        meta_store.upsert(
            fid="rejected_proposal.md",
            target="docs",
            title="Rejected Proposal",
            status="rejected",
            kind="proposal",
            timestamp=datetime.now(),
            content="Rejected content",
            context_json='{}'
        )

        # Only active_decision.md should be returned
        conflicts = meta_store.list_active_conflicts("docs")
        
        assert len(conflicts) == 1
        assert "active_decision.md" in conflicts
        assert "draft_proposal.md" not in conflicts
        assert "superseded_decision.md" not in conflicts
        assert "rejected_proposal.md" not in conflicts

    def test_no_conflicts_when_only_drafts(self, meta_store):
        """No conflicts should be returned when only draft records exist."""
        meta_store.upsert(
            fid="draft_proposal.md",
            target="docs",
            title="Draft Proposal",
            status="draft",
            kind="proposal",
            timestamp=datetime.now(),
            content="Draft content",
            context_json='{}'
        )

        conflicts = meta_store.list_active_conflicts("docs")
        
        assert len(conflicts) == 0

    def test_multiple_active_conflicts(self, meta_store):
        """Multiple active records for same target should all be returned."""
        meta_store.upsert(
            fid="active_1.md",
            target="api",
            title="Active 1",
            status="active",
            kind="decision",
            timestamp=datetime.now(),
            content="Content 1",
            context_json='{}'
        )
        meta_store.upsert(
            fid="active_2.md",
            target="api",
            title="Active 2",
            status="active",
            kind="proposal",
            timestamp=datetime.now(),
            content="Content 2",
            context_json='{}'
        )
        meta_store.upsert(
            fid="draft_1.md",
            target="api",
            title="Draft 1",
            status="draft",
            kind="proposal",
            timestamp=datetime.now(),
            content="Draft content",
            context_json='{}'
        )

        conflicts = meta_store.list_active_conflicts("api")
        
        assert len(conflicts) == 2
        assert "active_1.md" in conflicts
        assert "active_2.md" in conflicts
        assert "draft_1.md" not in conflicts

    def test_namespace_filtering(self, meta_store):
        """Conflicts should be filtered by namespace."""
        meta_store.upsert(
            fid="default_active.md",
            target="docs",
            title="Default Active",
            status="active",
            kind="decision",
            timestamp=datetime.now(),
            content="Default content",
            context_json='{}',
            namespace="default"
        )
        meta_store.upsert(
            fid="dev_active.md",
            target="docs",
            title="Dev Active",
            status="active",
            kind="decision",
            timestamp=datetime.now(),
            content="Dev content",
            context_json='{}',
            namespace="dev"
        )
        meta_store.upsert(
            fid="dev_draft.md",
            target="docs",
            title="Dev Draft",
            status="draft",
            kind="proposal",
            timestamp=datetime.now(),
            content="Dev draft content",
            context_json='{}',
            namespace="dev"
        )

        # Default namespace
        default_conflicts = meta_store.list_active_conflicts("docs", namespace="default")
        assert len(default_conflicts) == 1
        assert "default_active.md" in default_conflicts

        # Dev namespace
        dev_conflicts = meta_store.list_active_conflicts("docs", namespace="dev")
        assert len(dev_conflicts) == 1
        assert "dev_active.md" in dev_conflicts
        assert "dev_draft.md" not in dev_conflicts

    def test_knowledge_merge_target_excluded_in_integrity_check(self, meta_store):
        """
        I4 check should exclude knowledge_merge and knowledge_validation targets.
        This is handled in IntegrityChecker, not in list_active_conflicts.
        """
        # list_active_conflicts returns all active records regardless of target
        meta_store.upsert(
            fid="merge_active.md",
            target="knowledge_merge",
            title="Merge Active",
            status="active",
            kind="proposal",
            timestamp=datetime.now(),
            content="Merge content",
            context_json='{}'
        )

        conflicts = meta_store.list_active_conflicts("knowledge_merge")
        
        # list_active_conflicts returns it (IntegrityChecker filters it out later)
        assert len(conflicts) == 1
        assert "merge_active.md" in conflicts


class TestSemanticStoreListActiveConflicts:
    """Test list_active_conflicts in SemanticStore facade."""

    @pytest.fixture
    def semantic_store(self):
        """Create a temporary semantic store for testing."""
        repo_path = tempfile.mkdtemp()
        store = SemanticStore(repo_path=repo_path)
        yield store
        # Cleanup (SemanticStore doesn't have close() method)
        import shutil
        try:
            shutil.rmtree(repo_path)
        except Exception:
            pass

    def test_draft_not_in_conflicts(self, semantic_store):
        """Draft proposals should not appear in conflicts list."""
        # Manually insert into meta store
        semantic_store.meta.upsert(
            fid="draft_proposal.md",
            target="docs",
            title="Draft Proposal",
            status="draft",
            kind="proposal",
            timestamp=datetime.now(),
            content="Draft content",
            context_json='{}'
        )
        semantic_store.meta.upsert(
            fid="active_decision.md",
            target="docs",
            title="Active Decision",
            status="active",
            kind="decision",
            timestamp=datetime.now(),
            content="Active content",
            context_json='{}'
        )

        conflicts = semantic_store.list_active_conflicts("docs")
        
        assert len(conflicts) == 1
        assert "active_decision.md" in conflicts
        assert "draft_proposal.md" not in conflicts

    def test_empty_when_no_records(self, semantic_store):
        """Should return empty list when no records exist."""
        conflicts = semantic_store.list_active_conflicts("nonexistent")
        assert len(conflicts) == 0


class TestIntegrityCheckerWithDraftRecords:
    """Test IntegrityChecker correctly handles draft records."""

    @pytest.fixture
    def meta_store(self):
        """Create a temporary meta store for testing."""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store = SemanticMetaStore(db_path)
        yield store
        store.close()
        try:
            os.unlink(db_path)
            for ext in ["-wal", "-shm"]:
                if os.path.exists(db_path + ext):
                    os.unlink(db_path + ext)
        except Exception:
            pass

    def test_no_i4_violation_for_draft_with_same_target(self, meta_store):
        """
        Creating an active decision should not raise I4 violation
        when a draft proposal with the same target exists.
        """
        from ledgermind.core.stores.semantic_store.integrity import IntegrityViolation, IntegrityChecker

        # Insert a draft proposal
        meta_store.upsert(
            fid="draft_proposal.md",
            target="docs",
            title="Draft Proposal",
            status="draft",
            kind="proposal",
            timestamp=datetime.now(),
            content="Draft content",
            context_json='{}'
        )

        # This should NOT raise I4 violation because draft is not active
        # The integrity check is done via _validate_indexed which calls list_active_conflicts
        try:
            IntegrityChecker.validate(
                repo_path="/tmp/test",
                fid="new_active_decision.md",
                data={
                    "kind": "decision",
                    "status": "active",
                    "target": "docs",
                    "namespace": "default",
                    "context": {}
                },
                meta_store=meta_store
            )
            # No exception means test passed
            assert True
        except IntegrityViolation as e:
            pytest.fail(f"I4 violation raised incorrectly for draft: {e}")

    def test_i4_violation_for_active_with_same_target(self, meta_store):
        """
        Creating an active decision should raise I4 violation
        when an active decision with the same target already exists.
        """
        from ledgermind.core.stores.semantic_store.integrity import IntegrityViolation, IntegrityChecker

        # Insert an active decision
        meta_store.upsert(
            fid="existing_active.md",
            target="docs",
            title="Existing Active",
            status="active",
            kind="decision",
            timestamp=datetime.now(),
            content="Active content",
            context_json='{}'
        )

        # This SHOULD raise I4 violation
        with pytest.raises(IntegrityViolation) as exc_info:
            IntegrityChecker.validate(
                repo_path="/tmp/test",
                fid="new_active_decision.md",
                data={
                    "kind": "decision",
                    "status": "active",
                    "target": "docs",
                    "namespace": "default",
                    "context": {}
                },
                meta_store=meta_store
            )
        
        assert "I4 Violation" in str(exc_info.value)
        assert "docs" in str(exc_info.value)
