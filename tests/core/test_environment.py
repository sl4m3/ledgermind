import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import shutil
import subprocess
from ledgermind.core.api.memory import Memory

class TestEnvironmentCheck(unittest.TestCase):

    def setUp(self):
        pass

    @patch('ledgermind.core.api.memory.Memory.__init__', return_value=None)
    def test_check_environment_happy_path(self, mock_init):
        # Create a partial instance
        memory = Memory()
        memory.storage_path = "/tmp/test_storage"
        memory.semantic = MagicMock()
        memory.semantic.repo_path = "/tmp/test_storage/semantic"
        memory.trust_boundary = "agent_with_intent"
        memory.semantic.audit = MagicMock() # Default mock is not GitAuditProvider

        # Reset the class variable _git_available to force a check
        Memory._git_available = None

        with patch('ledgermind.core.api.memory.os.path.exists') as mock_exists, \
             patch('ledgermind.core.api.memory.os.access') as mock_access, \
             patch('ledgermind.core.api.memory.shutil.disk_usage') as mock_disk_usage, \
             patch('ledgermind.core.api.memory.subprocess.run') as mock_run, \
             patch('ledgermind.core.stores.vector.EMBEDDING_AVAILABLE', True, create=True):

            memory.config = MagicMock()
            memory.config.vector_model = "test_model.bin"

            # 1. Lock check (file does not exist)
            # 2. Storage path exists
            mock_exists.side_effect = lambda path: False if path.endswith('.lock') else True

            # Storage writable
            mock_access.return_value = True

            # Disk space ok
            usage_mock = MagicMock()
            usage_mock.free = 100 * 1024 * 1024 # 100 MB
            mock_disk_usage.return_value = usage_mock

            # Git check
            # First call: git --version (check=True)
            # Second call: git config user.name
            # Third call: git config user.email
            def run_side_effect(args, **kwargs):
                if args[0] == 'git':
                    if args[1] == '--version':
                        return MagicMock(returncode=0)
                    if args[1] == 'config':
                        return MagicMock(stdout="testuser\n")
                return MagicMock()

            mock_run.side_effect = run_side_effect

            # Act
            results = memory.check_environment()

            # Assert
            self.assertTrue(results["git_available"])
            self.assertTrue(results["git_configured"])
            self.assertTrue(results["storage_writable"])
            self.assertTrue(results["disk_space_ok"])
            self.assertTrue(results["vector_available"])
            self.assertFalse(results["storage_locked"])
            self.assertEqual(len(results["errors"]), 0)
            self.assertEqual(len(results["warnings"]), 0)

    @patch('ledgermind.core.api.memory.Memory.__init__', return_value=None)
    def test_check_environment_git_missing(self, mock_init):
        memory = Memory()
        memory.storage_path = "/tmp/test_storage"
        memory.semantic = MagicMock()
        memory.semantic.repo_path = "/tmp/test_storage/semantic"
        memory.trust_boundary = "agent_with_intent"

        Memory._git_available = None

        with patch('ledgermind.core.api.memory.os.path.exists', return_value=True), \
             patch('ledgermind.core.api.memory.os.access', return_value=True), \
             patch('ledgermind.core.api.memory.shutil.disk_usage') as mock_disk, \
             patch('ledgermind.core.api.memory.subprocess.run') as mock_run, \
             patch('ledgermind.core.stores.vector.EMBEDDING_AVAILABLE', True):

            mock_disk.return_value.free = 100 * 1024 * 1024

            # Git fails
            mock_run.side_effect = FileNotFoundError("git not found")

            results = memory.check_environment()

            self.assertFalse(results["git_available"])
            self.assertIn("Git is not installed", results["errors"][0])

    @patch('ledgermind.core.api.memory.Memory.__init__', return_value=None)
    def test_check_environment_git_not_configured(self, mock_init):
        memory = Memory()
        memory.storage_path = "/tmp/test_storage"
        memory.semantic = MagicMock()
        memory.semantic.repo_path = "/tmp/test_storage/semantic"
        memory.trust_boundary = "agent_with_intent"

        Memory._git_available = None

        with patch('ledgermind.core.api.memory.os.path.exists', return_value=True), \
             patch('ledgermind.core.api.memory.os.access', return_value=True), \
             patch('ledgermind.core.api.memory.shutil.disk_usage') as mock_disk, \
             patch('ledgermind.core.api.memory.subprocess.run') as mock_run, \
             patch('ledgermind.core.stores.vector.EMBEDDING_AVAILABLE', True):

            mock_disk.return_value.free = 100 * 1024 * 1024

            def run_side_effect(args, **kwargs):
                if args == ["git", "--version"]:
                    return MagicMock(returncode=0)
                if "config" in args:
                    return MagicMock(stdout="") # Empty config
                return MagicMock()

            mock_run.side_effect = run_side_effect

            results = memory.check_environment()

            self.assertTrue(results["git_available"])
            self.assertFalse(results["git_configured"])
            self.assertTrue(any("Git user.name" in w for w in results["warnings"]))

    @patch('ledgermind.core.api.memory.Memory.__init__', return_value=None)
    def test_check_environment_storage_not_writable(self, mock_init):
        memory = Memory()
        memory.storage_path = "/tmp/test_storage"
        memory.semantic = MagicMock()
        memory.semantic.repo_path = "/tmp/test_storage/semantic"
        memory.trust_boundary = "agent_with_intent"

        with patch('ledgermind.core.api.memory.os.path.exists', return_value=True), \
             patch('ledgermind.core.api.memory.os.access', return_value=False), \
             patch('ledgermind.core.api.memory.subprocess.run') as mock_run:

             # Git checks passed previously or mocked
             Memory._git_available = True
             mock_run.return_value.stdout = "config"

             results = memory.check_environment()

             self.assertFalse(results["storage_writable"])
             self.assertTrue(any("not writable" in e for e in results["errors"]))

    @patch('ledgermind.core.api.memory.Memory.__init__', return_value=None)
    def test_check_environment_low_disk_space(self, mock_init):
        memory = Memory()
        memory.storage_path = "/tmp/test_storage"
        memory.semantic = MagicMock()
        memory.semantic.repo_path = "/tmp/test_storage/semantic"
        memory.trust_boundary = "agent_with_intent"

        with patch('ledgermind.core.api.memory.os.path.exists', return_value=True), \
             patch('ledgermind.core.api.memory.os.access', return_value=True), \
             patch('ledgermind.core.api.memory.shutil.disk_usage') as mock_disk, \
             patch('ledgermind.core.api.memory.subprocess.run') as mock_run:

             Memory._git_available = True
             mock_run.return_value.stdout = "config"

             mock_disk.return_value.free = 10 * 1024 * 1024 # 10 MB

             results = memory.check_environment()

             self.assertFalse(results["disk_space_ok"])
             self.assertTrue(any("Low disk space" in w for w in results["warnings"]))

    @patch('ledgermind.core.api.memory.Memory.__init__', return_value=None)
    def test_check_environment_vector_unavailable(self, mock_init):
        memory = Memory()
        memory.storage_path = "/tmp/test_storage"
        memory.semantic = MagicMock()
        memory.semantic.repo_path = "/tmp/test_storage/semantic"
        memory.trust_boundary = "agent_with_intent"

        with patch('ledgermind.core.api.memory.os.path.exists', return_value=True), \
             patch('ledgermind.core.api.memory.os.access', return_value=True), \
             patch('ledgermind.core.api.memory.shutil.disk_usage') as mock_disk, \
             patch('ledgermind.core.api.memory.subprocess.run') as mock_run, \
             patch('ledgermind.core.stores.vector.LLAMA_AVAILABLE', False), \
             patch('ledgermind.core.stores.vector.EMBEDDING_AVAILABLE', False), \
             patch.dict('sys.modules', {'llama_cpp': MagicMock()}):

             Memory._git_available = True
             mock_run.return_value.stdout = "config"
             mock_disk.return_value.free = 100 * 1024 * 1024

             results = memory.check_environment()

             self.assertFalse(results["vector_available"])
             # The message varies based on which engine was checked first, but both contain "disabled"
             self.assertTrue(any("disabled" in w.lower() for w in results["warnings"]))
    @patch('ledgermind.core.api.memory.Memory.__init__', return_value=None)
    def test_check_environment_storage_locked(self, mock_init):
        memory = Memory()
        memory.storage_path = "/tmp/test_storage"
        memory.semantic = MagicMock()
        memory.semantic.repo_path = "/tmp/test_storage/semantic"
        memory.trust_boundary = "agent_with_intent"

        with patch('ledgermind.core.api.memory.os.path.exists') as mock_exists, \
             patch('ledgermind.core.api.memory.os.access', return_value=True), \
             patch('builtins.open', mock_open(read_data="12345")), \
             patch('ledgermind.core.api.memory.shutil.disk_usage') as mock_disk, \
             patch('ledgermind.core.api.memory.subprocess.run') as mock_run:

             # Simulate lock file existence
             def exists_side_effect(path):
                 if path.endswith('.lock'):
                     return True
                 return True
             mock_exists.side_effect = exists_side_effect

             Memory._git_available = True
             mock_run.return_value.stdout = "config"
             mock_disk.return_value.free = 100 * 1024 * 1024

             results = memory.check_environment()

             self.assertTrue(results["storage_locked"])
             self.assertEqual(results["lock_owner"], "12345")
             self.assertTrue(any("Storage is currently locked" in w for w in results["warnings"]))

    @patch('ledgermind.core.api.memory.Memory.__init__', return_value=None)
    def test_check_environment_repo_healthy(self, mock_init):
        from ledgermind.core.stores.audit_git import GitAuditProvider

        memory = Memory()
        memory.storage_path = "/tmp/test_storage"
        memory.semantic = MagicMock()
        memory.semantic.repo_path = "/tmp/test_storage/semantic"
        memory.trust_boundary = "agent_with_intent"

        # Mock audit provider as GitAuditProvider
        memory.semantic.audit = MagicMock(spec=GitAuditProvider)

        with patch('ledgermind.core.api.memory.os.path.exists', return_value=True), \
             patch('ledgermind.core.api.memory.os.access', return_value=True), \
             patch('ledgermind.core.api.memory.shutil.disk_usage') as mock_disk, \
             patch('ledgermind.core.api.memory.subprocess.run') as mock_run, \
             patch('ledgermind.core.stores.vector.EMBEDDING_AVAILABLE', True):

             Memory._git_available = True
             mock_run.return_value.stdout = "config"
             mock_disk.return_value.free = 100 * 1024 * 1024

             results = memory.check_environment()

             self.assertTrue(results["repo_healthy"])
             memory.semantic.audit.initialize.assert_called_once()

    @patch('ledgermind.core.api.memory.Memory.__init__', return_value=None)
    def test_check_environment_repo_unhealthy(self, mock_init):
        from ledgermind.core.stores.audit_git import GitAuditProvider

        memory = Memory()
        memory.storage_path = "/tmp/test_storage"
        memory.semantic = MagicMock()
        memory.semantic.repo_path = "/tmp/test_storage/semantic"
        memory.trust_boundary = "agent_with_intent"

        # Mock audit provider as GitAuditProvider
        memory.semantic.audit = MagicMock(spec=GitAuditProvider)
        memory.semantic.audit.initialize.side_effect = Exception("Repo init failed")

        with patch('ledgermind.core.api.memory.os.path.exists', return_value=True), \
             patch('ledgermind.core.api.memory.os.access', return_value=True), \
             patch('ledgermind.core.api.memory.shutil.disk_usage') as mock_disk, \
             patch('ledgermind.core.api.memory.subprocess.run') as mock_run, \
             patch('ledgermind.core.stores.vector.EMBEDDING_AVAILABLE', True):

             Memory._git_available = True
             mock_run.return_value.stdout = "config"
             mock_disk.return_value.free = 100 * 1024 * 1024

             results = memory.check_environment()

             self.assertFalse(results["repo_healthy"])
             self.assertTrue(any("Git repository initialization failed" in e for e in results["errors"]))
