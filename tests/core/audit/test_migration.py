import os
import pytest
from unittest.mock import MagicMock
from ledgermind.core.stores.semantic import SemanticStore
from ledgermind.core.core.schemas import TrustBoundary

def test_auto_migration_v1_22(temp_storage):
    sem_path = os.path.join(temp_storage, "semantic")
    os.makedirs(sem_path, exist_ok=True)
    
    # 1. Create a "Legacy" file (v1.11.0 style)
    # - No 'kind'
    # - target is too short (2 chars)
    # - rationale is too short
    legacy_file = "legacy_dec.md"
    content = """---
timestamp: '2026-01-01T00:00:00'
context:
  title: Old
  target: t1
  status: active
  rationale: short
---
# Old Content"""
    
    with open(os.path.join(sem_path, legacy_file), 'w') as f:
        f.write(content)
        
    # 2. Initialize SemanticStore (which triggers migration)
    store = SemanticStore(sem_path, trust_boundary=TrustBoundary.AGENT_WITH_INTENT)
    
    # 3. Verify changes
    with open(os.path.join(sem_path, legacy_file), 'r') as f:
        migrated_content = f.read()
        
    assert "kind: decision" in migrated_content
    assert "target: migrated_t1" in migrated_content
    assert "rationale: short (Migrated content)" in migrated_content
    assert "namespace: default" in migrated_content
    
    # 4. Verify SQLite index updated
    meta = store.meta.list_all()
    assert any(m['fid'] == legacy_file and m['target'] == 'migrated_t1' for m in meta)
