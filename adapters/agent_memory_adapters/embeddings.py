import os
import logging
from typing import List, Optional
from agent_memory_core.core.schemas import EmbeddingProvider

logger = logging.getLogger("agent-memory-multi.embeddings")

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Реализация EmbeddingProvider через OpenAI API."""
    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI()
        return self._client

    def get_embedding(self, text: str) -> List[float]:
        client = self._get_client()
        text = text.replace("\n", " ")
        return client.embeddings.create(input=[text], model=self.model).data[0].embedding

class GoogleEmbeddingProvider(EmbeddingProvider):
    """Реализация EmbeddingProvider через Google Generative AI API."""
    def __init__(self, model: str = "models/text-embedding-004"):
        self.model = model
        self._genai_module = None

    def _get_genai(self):
        if self._genai_module is None:
            import google.generativeai as genai
            self._genai_module = genai
        return self._genai_module

    def get_embedding(self, text: str) -> List[float]:
        genai = self._get_genai()
        result = genai.embed_content(
            model=self.model,
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']

class OllamaEmbeddingProvider(EmbeddingProvider):
    """Реализация EmbeddingProvider через локальный Ollama API."""
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "nomic-embed-text"):
        import requests
        self.base_url = base_url
        self.model = model
        self.requests = requests

    def get_embedding(self, text: str) -> List[float]:
        response = self.requests.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text}
        )
        response.raise_for_status()
        return response.json()["embedding"]

class MockEmbeddingProvider(EmbeddingProvider):
    """Заглушка для тестов или локальной работы без API."""
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def get_embedding(self, text: str) -> List[float]:
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        vec = []
        for i in range(self.dimension):
            val = ((h[i % len(h)] * (i + 1)) % 2000 - 1000) / 1000.0
            vec.append(val)
        return vec

class FallbackEmbeddingProvider(EmbeddingProvider):
    """
    Композитный провайдер с поддержкой отказоустойчивости.
    Перебирает список провайдеров до первого успешного ответа.
    """
    def __init__(self, providers: List[EmbeddingProvider]):
        self.providers = providers

    def get_embedding(self, text: str) -> List[float]:
        last_exception = None
        for provider in self.providers:
            try:
                return provider.get_embedding(text)
            except Exception as e:
                logger.warning(f"Embedding provider {provider.__class__.__name__} failed: {e}")
                last_exception = e
                continue
        
        logger.error("All embedding providers failed.")
        raise last_exception or RuntimeError("No embedding providers available")
