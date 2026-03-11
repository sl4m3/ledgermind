import pytest
import os
import time
from unittest.mock import patch
from ledgermind.core.stores.semantic import SemanticStore
from ledgermind.core.core.schemas import MemoryEvent

@pytest.fixture
def store(tmp_path):
    repo = tmp_path / "repo"
    os.makedirs(repo / "semantic")
    return SemanticStore(str(repo))

def test_content_hash_skips_parsing(store):
    """Verify that sync_meta_index skips parsing if content_hash matches."""
    # 1. Create a file
    event = MemoryEvent(
        source="user",
        kind="decision",
        content="Technical Rule",
        context={"title": "Rule V1", "target": "core/sync", "rationale": "Must be stable"}
    )
    fid = store.save(event)
    
    # Ensure it is indexed
    store.sync_meta_index(force=True)
    
    # 2. Get the initial metadata and its hash
    meta_v1 = store.meta.get_by_fid(fid)
    hash_v1 = meta_v1.get('content_hash')
    assert hash_v1 is not None
    
    # 3. Trigger sync again
    # Patch the actual module to ensure IntegrityChecker also uses the mock
    with patch("ledgermind.core.stores.semantic_store.loader.MemoryLoader.parse") as mock_parse:
        store.sync_meta_index()
        
        # Should NOT be called because hash matched
        assert mock_parse.call_count == 0
        
    # 4. Modify file manually
    time.sleep(1.1)
    full_path = os.path.join(store.repo_path, fid)
    with open(full_path, "a") as f:
        f.write("\nNew data")
        f.flush()
        os.fsync(f.fileno())
        
    # 5. Sync again
    # We patch BOTH locations just to be absolutely sure
    with patch("ledgermind.core.stores.semantic_store.loader.MemoryLoader.parse") as mock_parse:
        # Mocking parse to return valid data
        mock_parse.return_value = ({"kind": "decision", "context": {"title": "Rule V2", "target": "core/sync"}}, "Body")
        mock_parse.reset_mock()
        
        # Use regular sync. It should detect hash mismatch and call parse.
        store.sync_meta_index(force=False)
        
        # SHOULD be called because content changed (hash mismatch)
        assert mock_parse.call_count >= 1
