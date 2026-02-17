import os
import pytest
import tarfile
from unittest.mock import MagicMock, patch
from agent_memory_core.api.transfer import MemoryTransferManager

def test_export_import_tar(tmp_path):
    # Setup source
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "data.txt").write_text("hello world")
    
    manager = MemoryTransferManager(str(source_dir))
    tar_path = str(tmp_path / "backup.tar.gz")
    
    # Export
    exported = manager.export_to_tar(tar_path)
    assert os.path.exists(exported)
    assert exported.endswith(".tar.gz")
    
    # Import
    restore_dir = tmp_path / "restore"
    restore_dir.mkdir()
    manager.import_from_tar(exported, str(restore_dir / "source"))
    
    # Verify (shutil.extractall puts it in a subdir usually)
    restored_file = restore_dir / "source" / "data.txt"
    assert restored_file.exists()
    assert restored_file.read_text() == "hello world"

