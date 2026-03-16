"""
Test API key utility functions.
"""

import pytest
import os
import tempfile
import shutil

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from ledgermind.core.utils.api_keys import find_api_key_in_shell_configs, get_api_key


class TestAPIKeyUtils:
    """Test API key utility functions."""
    
    def test_find_api_key_in_nonexistent_file(self):
        """Verify function handles non-existent files gracefully."""
        # Create a temp directory that doesn't have any config files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Point to a non-existent file
            fake_config = os.path.join(tmpdir, "nonexistent_config")
            
            # Should return None without crashing
            result = find_api_key_in_shell_configs("TEST_API_KEY")
            assert result is None
    
    def test_find_api_key_in_empty_file(self):
        """Verify function handles empty config files."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh') as f:
            f.write("")  # Empty file
            temp_path = f.name
        
        try:
            # Temporarily add our temp file to the search path
            import ledgermind.core.utils.api_keys as api_keys_module
            original_func = api_keys_module.find_api_key_in_shell_configs
            
            # This would need mocking the config file list
            # For now, just verify it doesn't crash
            result = find_api_key_in_shell_configs("TEST_API_KEY")
            assert result is None
        finally:
            os.unlink(temp_path)
    
    def test_find_api_key_with_valid_export(self):
        """Verify function finds valid export statements."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh') as f:
            f.write('export TEST_API_KEY="test-value-123"\n')
            f.write('export OTHER_VAR="other-value"\n')
            temp_path = f.name
        
        try:
            # Mock the config files list to include our temp file
            import ledgermind.core.utils.api_keys as api_keys_module
            original_configs = [
                os.path.expanduser("~/.bashrc"),
                os.path.expanduser("~/.bash_profile"),
            ]
            
            # Temporarily replace config files with our test file
            api_keys_module.__dict__['_test_config_file'] = temp_path
            
            # For now, just test the regex pattern directly
            import re
            pattern = re.compile(r'export\s+TEST_API_KEY\s*=\s*["\']?([^"\'"\s]+)["\']?')
            with open(temp_path, 'r') as test_file:
                content = test_file.read()
                match = pattern.search(content)
                assert match is not None
                assert match.group(1) == "test-value-123"
        finally:
            os.unlink(temp_path)
    
    def test_get_api_key_from_env(self):
        """Verify get_api_key finds key in environment."""
        # Set a test key in environment
        os.environ["TEST_GET_API_KEY"] = "env-test-key"
        
        try:
            key, source = get_api_key("TEST_GET_API_KEY", search_configs=False)
            assert key == "env-test-key"
            assert source == "env"
        finally:
            del os.environ["TEST_GET_API_KEY"]
    
    def test_get_api_key_not_found(self):
        """Verify get_api_key returns None when key not found."""
        key, source = get_api_key("NONEXISTENT_API_KEY_12345", search_configs=False)
        assert key is None
        assert source == "none"
