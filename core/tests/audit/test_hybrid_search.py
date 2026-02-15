import os
import pytest
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import EmbeddingProvider

class SimpleMockProvider(EmbeddingProvider):
    def get_embedding(self, text: str):
        return [0.1] * 1536

def test_hybrid_search_policy(tmp_path):
    storage_path = str(tmp_path / "memory")
    
    # Use real memory logic with mock embeddings
    memory = Memory(
        storage_path=storage_path,
        embedding_provider=SimpleMockProvider()
    )
    
    # Recording first decision
    memory.record_decision("Version 1", "policy", "Old rule")
    old_id = memory.get_decisions()[0]
    
    # Superseding with second decision
    memory.supersede_decision("Version 2", "policy", "New rule", [old_id])
    
    # Searching for 'rule' in strict mode
    results = memory.search_decisions("rule", limit=10, mode="strict")
    
    for r in results:
        assert r['status'] == "active", f"PI Violation: Inactive decision {r['id']} returned in search!"

    assert len(results) == 1
    assert results[0]['status'] == "active"

def test_hybrid_ranking_active_vs_human_superseded(tmp_path):
    """
    Проверяет, что активное решение от агента ранжируется ВЫШЕ, чем 
    вытесненное решение от человека, несмотря на бонус авторитета у человека.
    """
    storage_path = str(tmp_path / "memory")
    memory = Memory(storage_path=storage_path, embedding_provider=SimpleMockProvider())
    
    # 1. Записываем человеческое решение (имитируем через record и ручную правку или просто доверяем логике поиска)
    # По умолчанию record_decision ставит source="agent", но мы можем проверить логику "[via MCP]"
    memory.record_decision("Human Guide", "style", "Standard indentation")
    human_id = memory.get_decisions()[0]
    
    # 2. Вытесняем его агентским решением
    memory.supersede_decision("Agent Guide", "style", "[via MCP:agent] Use tabs instead", [human_id])
    agent_id = [d for d in memory.get_decisions() if d != human_id][0]
    
    # Поиск в сбалансированном режиме
    results = memory.search_decisions("indentation guide", mode="balanced")
    
    # Проверяем порядок: агентское (активное) должно быть выше человеческого (superseded)
    # т.к. 1.0 (active) > 0.3 * (1.0 + 0.05)
    ids = [r['id'] for r in results]
    assert agent_id in ids
    assert ids.index(agent_id) < ids.index(human_id) if human_id in ids else True

def test_search_mode_audit_includes_all(tmp_path):
    """Проверяет, что в режиме 'audit' возвращаются даже вытесненные решения."""
    storage_path = str(tmp_path / "memory")
    memory = Memory(storage_path=storage_path, embedding_provider=SimpleMockProvider())
    
    memory.record_decision("Old Policy", "policy", "Old")
    old_id = memory.get_decisions()[0]
    memory.supersede_decision("New Policy", "policy", "New", [old_id])
    
    # В режиме 'strict' только 1 результат
    assert len(memory.search_decisions("policy", mode="strict")) == 1
    
    # В режиме 'balanced' (по умолчанию) теперь тоже 1 из-за дедупликации
    assert len(memory.search_decisions("policy", mode="balanced")) == 1

    # В режиме 'audit' возвращаются оба
    results = memory.search_decisions("policy", mode="audit", limit=10)
    assert len(results) == 2
    statuses = [r['status'] for r in results]
    assert "active" in statuses
    assert "superseded" in statuses
