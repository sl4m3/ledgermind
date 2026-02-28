import pytest
import os
import shutil
import numpy as np
from unittest.mock import MagicMock
from ledgermind.core.api.bridge import IntegrationBridge

@pytest.fixture
def temp_memory_path(tmp_path):
    path = tmp_path / "injection_test"
    os.makedirs(path, exist_ok=True)
    return str(path)

@pytest.fixture
def bridge(temp_memory_path):
    import ledgermind.core.stores.vector
    mock_model = MagicMock()
    def mock_encode(texts):
        embs = []
        for t in texts:
            v = np.zeros(384, dtype="float32")
            if "Python" in t or "coding" in t: v[0] = 1.0
            elif "Specific" in t: v[2] = 1.0
            else: v[10] = 1.0
            embs.append(v)
        return np.array(embs)
    mock_model.encode.side_effect = mock_encode
    mock_model.get_sentence_embedding_dimension.return_value = 384
    ledgermind.core.stores.vector._MODEL_CACHE["all-MiniLM-L6-v2"] = mock_model
    ledgermind.core.stores.vector.EMBEDDING_AVAILABLE = True
    return IntegrationBridge(memory_path=temp_memory_path, relevance_threshold=0.7, vector_model="all-MiniLM-L6-v2")

def test_injection_existence_check(bridge, temp_memory_path):
    bridge.record_decision(title="Project Rule", target="coding", rationale="Always use Python type hints for better quality.")
    context = bridge.get_context_for_prompt("How to write Python coding?")
    assert "[LEDGERMIND KNOWLEDGE BASE ACTIVE]" in context

def test_negative_filtering(bridge, temp_memory_path):
    # We test that irrelevant prompts do NOT trigger injection even if some data exists
    # Use a high threshold to be sure
    strict_bridge = IntegrationBridge(memory_path=temp_memory_path, relevance_threshold=0.99, vector_model="all-MiniLM-L6-v2")
    context = strict_bridge.get_context_for_prompt("How to cook pasta?")
    assert "[LEDGERMIND KNOWLEDGE BASE ACTIVE]" not in context

def test_threshold_behavior(bridge, temp_memory_path):
    bridge.memory.process_event(source="agent", kind="proposal", content="Specific Rule", context={"title": "Specific Rule", "target": "policy", "rationale": "Only admins can deploy to production.", "status": "active", "phase": "pattern"})
    prompt = "Who can deploy code?"
    high_bridge = IntegrationBridge(memory_path=temp_memory_path, relevance_threshold=1.0, vector_model="all-MiniLM-L6-v2")
    assert "[LEDGERMIND KNOWLEDGE BASE ACTIVE]" not in high_bridge.get_context_for_prompt(prompt)
