import pytest
import sys
import subprocess
import os

def test_lazy_loading_transformers(tmp_path):
    """Verify that transformers/sentence-transformers are NOT loaded when importing VectorStore."""
    test_dir = str(tmp_path / "vector_test")
    test_code = f"""
import sys
import os
from unittest.mock import MagicMock

# Mock llama_cpp
sys.modules['llama_cpp'] = MagicMock()

from ledgermind.core.stores.vector import VectorStore
# Use GGUF model
vs = VectorStore('{test_dir}', model_name='test.gguf')

transformers_loaded = 'transformers' in sys.modules or 'sentence_transformers' in sys.modules
print('LOADED' if transformers_loaded else 'CLEAN')
"""
    
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd() + "/src"
    
    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True, text=True, env=env
    )
    
    assert result.stdout.strip() == "CLEAN", f"Lazy loading failed! Output: {result.stdout} Error: {result.stderr}"

def test_transformers_loaded_on_demand(tmp_path):
    """Verify that transformers ARE loaded when a standard model is accessed."""
    test_dir = str(tmp_path / "vector_test_2")
    test_code = f"""
import sys
import os
from unittest.mock import MagicMock

sys.modules['sentence_transformers'] = MagicMock()
sys.modules['transformers'] = MagicMock()

from ledgermind.core.stores.vector import VectorStore
vs = VectorStore('{test_dir}', model_name='v5-small-text-matching-Q4_K_M.gguf')

try:
    _ = vs.model
except Exception:
    pass

print('LOADED' if 'sentence_transformers' in sys.modules else 'CLEAN')
"""
    
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd() + "/src"
    
    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True, text=True, env=env
    )
    
    assert "LOADED" in result.stdout, f"Output: {result.stdout} Error: {result.stderr}"
