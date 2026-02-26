import os
import shutil
import pytest
from ledgermind.server.tools.scanner import ProjectScanner

@pytest.fixture
def test_env():
    # Setup test environment
    base_dir = "test_valid_scan_env"
    if os.path.exists(base_dir):
        shutil.rmtree(base_dir)
    os.makedirs(base_dir)

    # Create dummy files
    with open(os.path.join(base_dir, "README.md"), "w") as f:
        f.write("# Valid Project")

    os.makedirs(os.path.join(base_dir, "src"))
    with open(os.path.join(base_dir, "src", "main.py"), "w") as f:
        f.write("print('Hello')")

    cwd = os.getcwd()
    os.chdir(base_dir)
    yield base_dir
    os.chdir(cwd)
    # shutil.rmtree(base_dir) # Keep for inspection if needed, or delete

def test_scan_current_directory(test_env):
    scanner = ProjectScanner(".")
    result = scanner.scan()
    assert "# Project Context Scan" in result
    assert "README.md" in result
    # ProjectScanner filters files, main.py is not in target_files.
    # But it lists directory structure.
    assert "src/" in result

def test_scan_subdirectory(test_env):
    scanner = ProjectScanner("src")
    result = scanner.scan()
    assert "# Project Context Scan" in result
    # main.py is not a target file, but should be listed in tree
    assert "main.py" in result

def test_scan_absolute_path_inside_cwd(test_env):
    abs_path = os.path.abspath("src")
    scanner = ProjectScanner(abs_path)
    result = scanner.scan()
    assert "# Project Context Scan" in result
    assert "main.py" in result

def test_scan_traversal_attack(test_env):
    with pytest.raises(ValueError, match="Access denied"):
        ProjectScanner("..")

def test_scan_absolute_path_outside_cwd():
    # This test assumes /tmp is outside the CWD (which is typically the repo root)
    outside_path = os.path.abspath("/tmp")
    cwd = os.path.abspath(os.getcwd())

    # Check if /tmp is not parent of cwd.
    # If cwd starts with /tmp, then /tmp is a parent, and access is denied anyway?
    # No, if CWD is /tmp/foo, then /tmp is outside CWD, so access should be denied.

    with pytest.raises(ValueError, match="Access denied"):
        ProjectScanner(outside_path)
