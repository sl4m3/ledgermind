import os
import pytest
from unittest.mock import MagicMock, patch
from ledgermind.core.api.memory import Memory

@pytest.mark.parametrize("disk_free_gb,expected_warning", [
    (100, False),
    (0.01, True) # 10MB should trigger warning (threshold is 50MB)
])
def test_check_environment_disk_space(tmp_path, disk_free_gb, expected_warning):
    storage = tmp_path / "storage"
    os.makedirs(storage)
    
    with patch('ledgermind.core.api.memory.VectorStore'), \
         patch('shutil.disk_usage') as mock_disk, \
         patch('os.access', return_value=True), \
         patch('subprocess.run') as mock_run:
        
        mock_disk.return_value = MagicMock(free=disk_free_gb * 1024 * 1024 * 1024)
        mock_run.return_value.stdout = "config"
        
        memory = Memory(str(storage))
        results = memory.check_environment()
        
        assert results["disk_space_ok"] == (not expected_warning)
        if expected_warning:
            assert any("Low disk space" in w for w in results["warnings"])

def test_check_environment_happy_path(tmp_path):
    storage = tmp_path / "happy_storage"
    os.makedirs(storage)
    
    with patch('ledgermind.core.api.memory.VectorStore'), \
         patch('shutil.disk_usage') as mock_disk, \
         patch('subprocess.run') as mock_run:
        
        mock_disk.return_value = MagicMock(free=10 * 1024 * 1024 * 1024)
        mock_run.return_value.stdout = "user"
        
        memory = Memory(str(storage))
        results = memory.check_environment()
        
        assert results["healthy"] is True
        assert results["storage_writable"] is True
        assert len(results["errors"]) == 0

def test_check_environment_not_writable(tmp_path):
    # Mocking os.access to return False for writability
    storage = tmp_path / "readonly_storage"
    os.makedirs(storage)
    
    with patch('ledgermind.core.api.memory.VectorStore'), \
         patch('os.access', return_value=False):
        
        memory = Memory(str(storage))
        results = memory.check_environment()
        
        assert results["storage_writable"] is False
        assert results["healthy"] is False
        assert any("not writable" in e for e in results["errors"])
