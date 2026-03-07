import pytest
import os
import json
from unittest.mock import MagicMock, patch
from ledgermind.core.reasoning.merging import MergeEngine
from ledgermind.core.core.schemas import KIND_PROPOSAL

@pytest.fixture
def mock_memory():
    m = MagicMock()
    m.semantic.repo_path = "/tmp/test_repo"
    m.semantic.meta = MagicMock()
    return m

@pytest.fixture
def merge_engine(mock_memory):
    return MergeEngine(mock_memory)

class TestMergingArchitecture:
    @patch("os.path.join")
    @patch("builtins.open")
    @patch("ledgermind.core.stores.semantic_store.loader.MemoryLoader.parse")
    def test_scan_for_duplicates_creates_proposal(self, mock_parse, mock_open, mock_join, merge_engine, mock_memory):
        """Verify that MergeEngine detects near-identical documents and creates a merge proposal."""
        # 1. Setup mock metadata for two identical documents in the same architectural branch
        # Long titles ensure high Jaccard score even after noise removal
        title = "Persistent Storage Implementation for SQLite and Filesystem"
        mock_memory.get_decisions.return_value = ["dec1.md", "dec2.md"]
        mock_memory.semantic.meta.list_all.return_value = [
            {
                "fid": "dec1.md", "target": "core/storage_v1", "title": title, 
                "status": "active", "kind": "decision", "enrichment_status": "completed", 
                "timestamp": "2026-03-07T00:00:00"
            },
            {
                "fid": "dec2.md", "target": "core/storage_v2", "title": title, 
                "status": "active", "kind": "decision", "enrichment_status": "completed", 
                "timestamp": "2026-03-07T00:00:00"
            }
        ]

        # 2. Mock search to return:
        # - The document itself (required for self_score calculation)
        # - The other document as a perfect match
        mock_memory.search_decisions.return_value = [
            {"id": "dec1.md", "score": 1.0, "similarity_score": 1.0, "title": title, "target": "core/storage_v1"},
            {"id": "dec2.md", "score": 0.99, "similarity_score": 0.99, "title": title, "target": "core/storage_v2"}
        ]
        
        # 3. Mock file parsing for initial candidate
        mock_parse.return_value = ({"content": "Storage logic", "context": {"title": title, "target": "core/storage_v1"}}, "Body")
        
        # 4. Mock proposal creation response
        mock_memory.process_event.return_value = MagicMock(metadata={"file_id": "merge_prop_1.md"})

        # 5. Run scan
        proposals = merge_engine.scan_for_duplicates(threshold=0.85)
        
        # 6. Verify result
        assert len(proposals) == 1
        mock_memory.search_decisions.assert_called()
        
        # Verify that Architectural Guard passed (same branch core/) 
        # and Jaccard passed (identical titles)
        call_args = mock_memory.process_event.call_args
        assert call_args[1]["kind"] == KIND_PROPOSAL
        assert "dec1.md" in call_args[1]["context"]["suggested_supersedes"]
        assert "dec2.md" in call_args[1]["context"]["suggested_supersedes"]

    def test_architectural_guard_blocks_cross_branch_merges(self, merge_engine, mock_memory):
        """Verify that documents in different branches (e.g. core vs docs) are NEVER merged."""
        title = "Security Best Practices and Implementation"
        mock_memory.semantic.meta.list_all.return_value = [
            {
                "fid": "core_sec.md", "target": "core/security", "title": title, 
                "status": "active", "kind": "decision", "enrichment_status": "completed", 
                "timestamp": "2026-03-07T00:00:00"
            }
        ]
        # Search returns a document with identical title but different branch
        mock_memory.search_decisions.return_value = [
            {"id": "docs_sec.md", "score": 1.0, "similarity_score": 1.0, "title": title, "target": "docs/security"}
        ]
        
        # This should result in 0 proposals despite perfect Sim 1.0
        proposals = merge_engine.scan_for_duplicates(threshold=0.5)
        assert len(proposals) == 0
