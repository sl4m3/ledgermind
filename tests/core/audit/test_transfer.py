import os
import pytest
import tarfile
from unittest.mock import MagicMock, patch
from ledgermind.core.api.transfer import MemoryTransferManager

def test_export_import_tar(tmp_path):
    # Setup source
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "data.txt").write_text("hello world")
    
    manager = MemoryTransferManager(str(source_dir))
    tar_path = "backup.tar.gz"
    
    # Export
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        exported = manager.export_to_tar(tar_path)
        assert os.path.exists(exported)
        assert exported.endswith(".tar.gz")

        # Import
        restore_dir = tmp_path / "restore"
        restore_dir.mkdir()
        manager.import_from_tar(exported, str(restore_dir / "source"))
    finally:
        os.chdir(cwd)
    
    # Verify (shutil.extractall puts it in a subdir usually)
    restored_file = restore_dir / "source" / "data.txt"
    assert restored_file.exists()
    assert restored_file.read_text() == "hello world"

def test_export_security_violation(tmp_path):
    manager = MemoryTransferManager(str(tmp_path))

    # Test absolute path
    with pytest.raises(ValueError, match="Security violation"):
        manager.export_to_tar("/tmp/unsafe.tar.gz")

    # Test directory traversal
    with pytest.raises(ValueError, match="Security violation"):
        manager.export_to_tar("../unsafe.tar.gz")

    # Test subdirectory
    with pytest.raises(ValueError, match="Security violation"):
        manager.export_to_tar("subdir/unsafe.tar.gz")
