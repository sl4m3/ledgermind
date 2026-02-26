import os
import shutil
import tempfile
import unittest
from ledgermind.server.tools.scanner import ProjectScanner

class TestProjectScanner(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for each test
        self.test_dir = tempfile.mkdtemp()
        self.scanner = ProjectScanner(root_path=self.test_dir)

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    def _create_file(self, path, content):
        full_path = os.path.join(self.test_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def _create_large_file(self, path, size_bytes):
        full_path = os.path.join(self.test_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as f:
            f.write(b'a' * size_bytes)

    def test_scan_basic_structure(self):
        """Test basic directory structure scanning and key file content reading."""
        self._create_file('README.md', '# Test Project\nDescription.')
        self._create_file('src/main.py', 'print("Hello")')
        self._create_file('.git/config', '[core]\nrepositoryformatversion = 0')

        report = self.scanner.scan()

        # Verify structure
        self.assertIn('- README.md', report)
        self.assertIn('- src/', report)
        self.assertIn('  - main.py', report)

        # Verify ignored directory is not present
        self.assertNotIn('.git', report)

        # Verify file content
        self.assertIn('### README.md', report)
        self.assertIn('# Test Project', report)

    def test_scan_ignored_directories(self):
        """Test that specified directories are ignored."""
        self._create_file('node_modules/package.json', '{}')
        self._create_file('venv/bin/activate', 'echo "activate"')
        self._create_file('src/app.py', 'print("app")')

        report = self.scanner.scan()

        self.assertNotIn('node_modules', report)
        self.assertNotIn('venv', report)
        self.assertIn('src/', report)

    def test_scan_max_depth(self):
        """Test that scanning stops at max_depth."""
        # Default max_depth is 7
        # Create deep structure: a/b/c/d/e/f/g/h/i/j (depth 10)
        deep_path = 'a/b/c/d/e/f/g/h/i/j'
        self._create_file(os.path.join(deep_path, 'deep_file.txt'), 'content')

        report = self.scanner.scan()

        # Depth 1: a/
        self.assertIn('- a/', report)
        # Depth 7 should be visible, depth 8+ should not
        # Structure: root -> a (1) -> b (2) -> c (3) -> d (4) -> e (5) -> f (6) -> g (7) -> h (8)

        # Let's verify specifically what is visible.
        # scanner logic: depth = rel_path.count(os.sep) + 1
        # if depth > self.max_depth: continue

        # a is depth 1.
        # ...
        # g is depth 7.
        # h is depth 8.

        self.assertIn('- g/', report)
        self.assertNotIn('- h/', report)

    def test_scan_file_size_limit(self):
        """Test that files exceeding size limit are skipped."""
        # max_file_size is 64KB
        large_file_path = 'large_file.txt'
        # Create a file slightly larger than 64KB
        self._create_large_file(large_file_path, 64 * 1024 + 10)

        # Add to target_files to ensure it's considered for content reading
        self.scanner.target_files.add(large_file_path)

        report = self.scanner.scan()

        self.assertIn('large_file.txt', report) # It should be in the tree
        self.assertIn('File skipped: Exceeds size limit', report) # Content skipped

    def test_scan_content_truncation(self):
        """Test that large file content is truncated."""
        long_file_path = 'long_file.md'
        # Create content > 6000 chars
        content = 'a' * 6001
        self._create_file(long_file_path, content)

        report = self.scanner.scan()

        self.assertIn('...[Truncated due to length]...', report)
        # Verify the content length in report is roughly 6000 + message length
        # We can't be exact due to other report text, but we can check it's there.

    def test_empty_directory(self):
        """Test scanning an empty directory."""
        report = self.scanner.scan()
        # Even an empty directory has the root './'
        self.assertIn('- ./', report)
        self.assertIn('No standard key files found.', report)

    def test_scan_custom_target_files(self):
        """Test scanning with custom target files."""
        self._create_file('custom.config', 'secret=true')
        self.scanner.target_files.add('custom.config')

        report = self.scanner.scan()

        self.assertIn('### custom.config', report)
        self.assertIn('secret=true', report)
