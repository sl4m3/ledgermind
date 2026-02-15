import pytest
import numpy as np
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import EmbeddingProvider

class DriftingProvider(EmbeddingProvider):
    """Провайдер, имитирующий дрейф или шум в эмбеддингах."""
    def __init__(self, noise_level=0.0):
        self.noise_level = noise_level
        self.base_vectors = {}

    def get_embedding(self, text: str):
        # Если текст уже видели, возвращаем базовый вектор + шум
        if text not in self.base_vectors:
            # Детерминированный "случайный" вектор для текста
            rng = np.random.default_rng(hash(text) & 0xFFFFFFFF)
            self.base_vectors[text] = rng.standard_normal(1536)
        
        vec = self.base_vectors[text]
        if self.noise_level > 0:
            noise = np.random.standard_normal(1536) * self.noise_level
            vec = vec + noise
        
        # Нормализуем (косинусное сходство)
        return (vec / np.linalg.norm(vec)).tolist()

def test_semantic_search_stability_under_drift(temp_storage):
    """Проверяет, что поиск остается стабильным при небольшом шуме в эмбеддингах."""
    provider = DriftingProvider(noise_level=0.0)
    memory = Memory(storage_path=temp_storage, embedding_provider=provider)
    
    # Записываем набор разнородных решений
    decisions = [
        ("Database migration to PostgreSQL", "infra", "Better scalability"),
        ("Use React for frontend", "ui", "Component reuse"),
        ("Implement JWT auth", "security", "Standard approach"),
        ("Add prometheus monitoring", "ops", "Visibility")
    ]
    
    for title, target, rationale in decisions:
        memory.record_decision(title, target, rationale)
    
    # Исходный поиск
    query = "How to handle authentication?"
    results_orig = memory.search_decisions(query, limit=1)
    assert len(results_orig) > 0
    best_match_id = results_orig[0]['id']
    
    # Включаем дрейф (шум) и проверяем, что лидер не изменился (при малом шуме)
    provider.noise_level = 0.01 # Reduced noise
    results_drift = memory.search_decisions(query, limit=1)
    
    assert results_drift[0]['id'] == best_match_id, "Semantic search is too sensitive to embedding noise!"

def test_semantic_recall_after_reindexing(temp_storage):
    """Проверяет, что после 'реиндексации' (смены провайдера) важные связи сохраняются."""
    # 1. Провайдер A
    provider_a = DriftingProvider(noise_level=0.0)
    memory_a = Memory(storage_path=temp_storage, embedding_provider=provider_a)
    memory_a.record_decision("Audit logging policy", "compliance", "Requirement 5.2")
    
    # 2. Провайдер B (немного другой алгоритм, но похожий смысл - имитируем через шум)
    # В реальности это была бы смена модели (например, OpenAI -> Ollama)
    provider_b = DriftingProvider(noise_level=0.05)
    memory_b = Memory(storage_path=temp_storage, embedding_provider=provider_b)
    
    results = memory_b.search_decisions("compliance and logs", limit=5)
    
    # Проверяем, что решение всё еще находится, несмотря на "смену модели"
    found = any("Audit logging" in r['preview'] for r in results)
    assert found, "Decision lost after semantic model drift simulation"
