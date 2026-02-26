import os
import json
import pytest
import tempfile
from ledgermind.core.core.targets import TargetRegistry

@pytest.fixture(autouse=True)
def clean_registry_cache():
    """Ensure the registry cache is cleared before and after each test."""
    TargetRegistry._cache.clear()
    yield
    TargetRegistry._cache.clear()

def test_registry_initialization():
    """Test that the registry is a singleton per path and handles initialization correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry1 = TargetRegistry(temp_dir)
        registry2 = TargetRegistry(temp_dir)

        # Verify singleton behavior
        assert registry1 is registry2
        assert registry1.storage_path == os.path.abspath(temp_dir)

        # Verify distinct paths yield distinct instances
        with tempfile.TemporaryDirectory() as temp_dir2:
            registry3 = TargetRegistry(temp_dir2)
            assert registry1 is not registry3

def test_register_and_persistence():
    """Test registering targets and persisting them to disk."""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry = TargetRegistry(temp_dir)

        # Register a target
        registry.register("TestTarget", "Description", aliases=["tt", "test"])

        # Verify in-memory state
        assert "TestTarget" in registry.targets
        assert registry.aliases["tt"] == "TestTarget"
        assert registry.aliases["test"] == "TestTarget"

        # Verify file persistence
        file_path = os.path.join(temp_dir, "targets.json")
        assert os.path.exists(file_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert "TestTarget" in data["targets"]
            assert data["aliases"]["tt"] == "TestTarget"

        # Clear cache and reload from disk (simulating restart)
        TargetRegistry._cache.clear()
        new_registry = TargetRegistry(temp_dir)

        assert "TestTarget" in new_registry.targets
        assert new_registry.aliases["tt"] == "TestTarget"
        assert new_registry.targets["TestTarget"]["description"] == "Description"

def test_normalization():
    """Test normalization logic including exact, alias, and case-insensitive matches."""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry = TargetRegistry(temp_dir)
        registry.register("PrimaryTarget", aliases=["pt", "alias1"])
        registry.register("AnotherTarget")

        # Exact match
        assert registry.normalize("PrimaryTarget") == "PrimaryTarget"

        # Alias match
        assert registry.normalize("pt") == "PrimaryTarget"
        assert registry.normalize("alias1") == "PrimaryTarget"

        # Case-insensitive match (target)
        assert registry.normalize("primarytarget") == "PrimaryTarget"
        assert registry.normalize("PRIMARYTARGET") == "PrimaryTarget"

        # Case-insensitive match (alias)
        assert registry.normalize("PT") == "PrimaryTarget"
        assert registry.normalize("Alias1") == "PrimaryTarget"

        # Unknown target
        assert registry.normalize("UnknownTarget") == "UnknownTarget"

        # Empty input
        assert registry.normalize("") == "unknown"
        assert registry.normalize("   ") == "unknown"

def test_suggest():
    """Test suggestions for similar target names."""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry = TargetRegistry(temp_dir)
        registry.register("apple")
        registry.register("application")
        registry.register("apply")
        registry.register("banana")

        suggestions = registry.suggest("app", limit=3)
        assert "apple" in suggestions or "apply" in suggestions or "application" in suggestions
        assert "banana" not in suggestions

        # Exact match should also be suggested if close enough (get_close_matches logic)
        suggestions = registry.suggest("apple")
        assert "apple" in suggestions

def test_corrupted_file():
    """Test that the registry handles corrupted JSON files gracefully."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, "targets.json")

        # Create a corrupted file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("{invalid_json")

        # Should initialize with empty registry and log error (implicitly checked by lack of exception)
        registry = TargetRegistry(temp_dir)
        assert registry.targets == {}
        assert registry.aliases == {}

        # Should be able to overwrite the corrupted file on new registration
        registry.register("NewTarget")

        # Reload to verify it was fixed
        TargetRegistry._cache.clear()
        registry_reloaded = TargetRegistry(temp_dir)
        assert "NewTarget" in registry_reloaded.targets

def test_register_updates_file():
    """Test that register updates the file immediately."""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry = TargetRegistry(temp_dir)
        file_path = os.path.join(temp_dir, "targets.json")

        assert not os.path.exists(file_path)

        registry.register("Target1")
        assert os.path.exists(file_path)

        last_mtime = os.path.getmtime(file_path)

        # Register another target
        registry.register("Target2")

        # Check that file content is updated
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert "Target1" in data["targets"]
            assert "Target2" in data["targets"]
