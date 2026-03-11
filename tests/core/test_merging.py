import pytest
from unittest.mock import MagicMock, patch
from ledgermind.core.reasoning.merging import MergeEngine

@pytest.fixture
def mock_memory():
    m = MagicMock()
    m.semantic.repo_path = "/tmp/test_repo"
    m.semantic.meta = MagicMock()
    
    # Meta Store should have the candidates
    m.semantic.meta.get_by_fid.side_effect = lambda fid: {
        "dec1.md": {"fid": "dec1.md", "target": "core/storage_v1", "title": "Persistent Storage Implementation for SQLite and Filesystem", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "timestamp": "2026-03-07T00:00:00"},
        "dec2.md": {"fid": "dec2.md", "target": "core/storage_v2", "title": "Persistent Storage Implementation for SQLite and Filesystem", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "timestamp": "2026-03-07T00:00:00"},
        "core_sec.md": {"fid": "core_sec.md", "target": "core/security", "title": "Security Best Practices and Implementation", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "timestamp": "2026-03-07T00:00:00"},
        "docs_sec.md": {"fid": "docs_sec.md", "target": "docs/security", "title": "Security Best Practices and Implementation", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "timestamp": "2026-03-07T00:00:00"}
    }.get(fid)
    
    # Simulate resolve_to_truth
    m._resolve_to_truth.side_effect = lambda fid, mode, cache: {
        "dec1.md": {"fid": "dec1.md", "target": "core/storage_v1", "title": "Persistent Storage Implementation for SQLite and Filesystem", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "timestamp": "2026-03-07T00:00:00"},
        "dec2.md": {"fid": "dec2.md", "target": "core/storage_v2", "title": "Persistent Storage Implementation for SQLite and Filesystem", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "timestamp": "2026-03-07T00:00:00"},
        "core_sec.md": {"fid": "core_sec.md", "target": "core/security", "title": "Security Best Practices and Implementation", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "timestamp": "2026-03-07T00:00:00"},
        "docs_sec.md": {"fid": "docs_sec.md", "target": "docs/security", "title": "Security Best Practices and Implementation", "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle", "timestamp": "2026-03-07T00:00:00"}
    }.get(fid)
    
    return m

@pytest.fixture
def merge_engine(mock_memory):
    return MergeEngine(mock_memory)

class TestMergingArchitecture:
    @patch("ledgermind.core.stores.semantic_store.loader.MemoryLoader.parse")
    def test_scan_for_duplicates_creates_proposal(self, mock_parse, merge_engine, mock_memory):
        """Verify that MergeEngine detects near-identical documents and creates a merge proposal."""
        title = "Persistent Storage Implementation for SQLite and Filesystem"
        mock_memory.semantic.meta.list_all.return_value = [
            {
                "fid": "dec1.md", "target": "core/storage_v1", "title": title, 
                "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle",
                "timestamp": "2026-03-07T00:00:00"
            }
        ]

        # Mock vector search to return the other document
        mock_memory.vector.search.return_value = [
            {"id": "dec2.md", "score": 0.99}
        ]
        
        # Patch the algorithm created inside MergeEngineFacade
        with patch("ledgermind.core.reasoning.merging.facade.AlgorithmFactory.create") as mock_factory:
            mock_alg = MagicMock()
            mock_alg.calculate_similarity.return_value = 0.99
            mock_alg._get_doc_text.return_value = "Storage logic"
            mock_factory.return_value = mock_alg
            merge_engine._facade.algorithm = mock_alg
            
            mock_parse.return_value = ({"content": "Storage logic", "context": {"title": title, "target": "core/storage_v1"}}, "Body")
            
            # The transaction manager needs to successfully return an ID
            mock_memory.semantic.meta.get_config.return_value = None
            mock_memory.process_event.return_value = MagicMock(should_persist=True, metadata={"file_id": "merge_prop_1.md"})
            
            # Allow record_decision to succeed inside the transaction manager
            mock_memory.record_decision.return_value = MagicMock(metadata={"file_id": "merge_prop_1.md"})

            proposals = merge_engine.scan_for_duplicates(threshold=0.85)
            
            assert len(proposals) == 1

    @patch("ledgermind.core.stores.semantic_store.loader.MemoryLoader.parse")
    def test_architectural_guard_blocks_cross_branch_merges(self, mock_parse, merge_engine, mock_memory):
        """Verify that documents in different branches (e.g. core vs docs) are NEVER merged."""
        title = "Security Best Practices and Implementation"
        mock_memory.semantic.meta.list_all.return_value = [
            {
                "fid": "core_sec.md", "target": "core/security", "title": title, 
                "status": "active", "kind": "decision", "enrichment_status": "completed", "merge_status": "idle",
                "timestamp": "2026-03-07T00:00:00"
            }
        ]
        mock_memory.vector.search.return_value = [
            {"id": "docs_sec.md", "score": 1.0}
        ]
        
        with patch("ledgermind.core.reasoning.merging.facade.AlgorithmFactory.create") as mock_factory:
            mock_alg = MagicMock()
            mock_alg.calculate_similarity.return_value = 0.1 # Semantic sim is perfect but target penalty applied
            mock_alg._get_doc_text.return_value = "Sec logic"
            mock_factory.return_value = mock_alg
            merge_engine._facade.algorithm = mock_alg
            
            mock_parse.return_value = ({"content": "Sec logic", "context": {"title": title, "target": "core/security"}}, "Body")

            proposals = merge_engine.scan_for_duplicates(threshold=0.5)
            assert len(proposals) == 0