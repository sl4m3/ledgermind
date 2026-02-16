import pytest
from unittest.mock import MagicMock, patch
from agent_memory_adapters.embeddings import (
    MockEmbeddingProvider, 
    FallbackEmbeddingProvider,
    OpenAIEmbeddingProvider,
    OllamaEmbeddingProvider
)

def test_mock_embedding_provider():
    provider = MockEmbeddingProvider(dimension=10)
    emb = provider.get_embedding("test")
    assert len(emb) == 10
    assert isinstance(emb[0], float)
    
    # Deterministic check
    emb2 = provider.get_embedding("test")
    assert emb == emb2

def test_fallback_embedding_provider():
    p1 = MagicMock()
    p1.get_embedding.side_effect = Exception("Fail")
    
    p2 = MagicMock()
    p2.get_embedding.return_value = [0.1, 0.2]
    
    fallback = FallbackEmbeddingProvider([p1, p2])
    res = fallback.get_embedding("test")
    
    assert res == [0.1, 0.2]
    assert p1.get_embedding.called
    assert p2.get_embedding.called

@patch("openai.OpenAI")
def test_openai_embedding_provider(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    
    mock_resp = MagicMock()
    mock_resp.data = [MagicMock(embedding=[0.5, 0.6])]
    mock_client.embeddings.create.return_value = mock_resp
    
    provider = OpenAIEmbeddingProvider()
    res = provider.get_embedding("hello")
    
    assert res == [0.5, 0.6]
    mock_client.embeddings.create.assert_called_once()

@patch("requests.post")
def test_ollama_embedding_provider(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embedding": [0.7, 0.8]}
    mock_post.return_value = mock_resp
    
    provider = OllamaEmbeddingProvider()
    res = provider.get_embedding("prompt")
    
    assert res == [0.7, 0.8]
    assert mock_post.called
