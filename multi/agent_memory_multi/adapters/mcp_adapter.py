from typing import Any, Dict, List, Optional
import json
from mcp.server.fastmcp import FastMCP
from agent_memory_multi.manager import MemoryMultiManager

class MCPMemoryAdapter:
    """
    Адаптер Model Context Protocol (MCP).
    Предоставляет возможности памяти как инструменты для любого MCP-клиента.
    Работает как RPC-прокси над MemoryMultiManager.
    """

    def __init__(self, manager: MemoryMultiManager, server_name: str = "AgentMemory"):
        self.manager = manager
        # FastMCP предоставляет высокоуровневый интерфейс для создания MCP серверов
        self.mcp = FastMCP(server_name)
        self._register_tools()

    def _register_tools(self):
        """
        Регистрирует инструменты в MCP сервере.
        Использует FastMCP декораторы для автоматического формирования схем.
        """

        @self.mcp.tool()
        def record_decision(title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> str:
            """
            Записывает стратегическое решение в долгосрочную семантическую память.
            
            Args:
                title: Краткий заголовок решения.
                target: Область применения (например, 'auth', 'database').
                rationale: Обоснование решения.
                consequences: Список ожидаемых последствий (опционально).
            """
            args = {
                "title": title,
                "target": target,
                "rationale": rationale,
                "consequences": consequences or []
            }
            result = self.manager.handle_tool_call("record_decision", args)
            return json.dumps(result, ensure_ascii=False)

        @self.mcp.tool()
        def supersede_decision(title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> str:
            """
            Заменяет старые решения новым, обновляя семантическую память.
            
            Args:
                title: Заголовок нового решения.
                target: Область применения.
                rationale: Почему старые решения заменяются.
                old_decision_ids: Список ID заменяемых решений.
                consequences: Новые последствия (опционально).
            """
            args = {
                "title": title,
                "target": target,
                "rationale": rationale,
                "old_decision_ids": old_decision_ids,
                "consequences": consequences or []
            }
            result = self.manager.handle_tool_call("supersede_decision", args)
            return json.dumps(result, ensure_ascii=False)

        @self.mcp.tool()
        def list_active_decisions() -> str:
            """
            Возвращает список идентификаторов всех активных решений в памяти.
            """
            if not self.manager.core:
                return json.dumps({"status": "error", "message": "Core memory not initialized"})
            
            decisions = self.manager.core.get_decisions()
            return json.dumps({"status": "success", "decisions": decisions}, ensure_ascii=False)

        @self.mcp.tool()
        def get_recent_history(limit: int = 5) -> str:
            """
            Возвращает последние события из эпизодической памяти.
            """
            if not self.manager.core:
                return json.dumps({"status": "error", "message": "Core memory not initialized"})
            
            history = self.manager.core.get_recent_events(limit=limit)
            return json.dumps({"status": "success", "history": history}, ensure_ascii=False)

        @self.mcp.tool()
        def search_decisions(query: str, limit: int = 5) -> str:
            """
            Семантический поиск по принятым решениям.
            Позволяет найти релевантные правила и договоренности по смыслу запроса.
            """
            if not self.manager.core:
                return json.dumps({"status": "error", "message": "Core memory not initialized"})
            
            results = self.manager.core.search_decisions(query, limit=limit)
            return json.dumps({"status": "success", "results": results}, ensure_ascii=False)

        @self.mcp.tool()
        def capture_context(label: str = "general_context") -> str:
            """
            Делает снимок текущего окружения (файлы, состояние git) и сохраняет его в эпизодическую память.
            Это позволяет агенту 'запомнить' состояние проекта в конкретный момент времени.
            """
            result = self.manager.handle_tool_call("capture_context", {"label": label})
            return json.dumps(result, ensure_ascii=False)

        @self.mcp.tool()
        def sync_git_history(repo_path: str = ".", limit: int = 20) -> str:
            """
            Синхронизирует историю коммитов Git с эпизодической памятью.
            Это позволяет системе учитывать изменения кода, сделанные людьми, при рефлексии.
            """
            if not self.manager.core:
                return json.dumps({"status": "error", "message": "Core memory not initialized"})
            
            count = self.manager.core.sync_git(repo_path=repo_path, limit=limit)
            return json.dumps({"status": "success", "indexed_commits": count}, ensure_ascii=False)

        @self.mcp.tool()
        def run_reflection() -> str:
            """
            Запускает процесс саморефлексии для поиска паттернов и генерации предложений (Proposals).
            """
            if not self.manager.core:
                return json.dumps({"status": "error", "message": "Core memory not initialized"})
            
            proposals = self.manager.core.run_reflection()
            return json.dumps({"status": "success", "created_proposals": proposals}, ensure_ascii=False)

        @self.mcp.tool()
        def accept_proposal(proposal_id: str) -> str:
            """
            Принимает предложение и превращает его в активное семантическое решение.
            """
            if not self.manager.core:
                return json.dumps({"status": "error", "message": "Core memory not initialized"})
            
            result = self.manager.core.accept_proposal(proposal_id)
            return json.dumps({"status": "success", "message": "Proposal accepted"}, ensure_ascii=False)

        @self.mcp.tool()
        def reject_proposal(proposal_id: str, reason: str) -> str:
            """
            Отклоняет предложение.
            """
            if not self.manager.core:
                return json.dumps({"status": "error", "message": "Core memory not initialized"})
            
            self.manager.core.reject_proposal(proposal_id, reason)
            return json.dumps({"status": "success", "message": "Proposal rejected"}, ensure_ascii=False)

    def run(self):
        """Запускает MCP сервер."""
        self.mcp.run()

    @classmethod
    def serve(cls, storage_path: str = ".agent_memory", server_name: str = "AgentMemory"):
        """
        Упрощенный запуск MCP сервера 'из коробки'.
        Автоматически инициализирует все компоненты.
        """
        import os
        from agent_memory_core.api.memory import Memory
        from agent_memory_multi.manager import MemoryMultiManager
        from agent_memory_multi.embeddings import MockEmbeddingProvider

        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)

        core = Memory(
            storage_path=storage_path,
            embedding_provider=MockEmbeddingProvider()
        )
        manager = MemoryMultiManager(core)
        adapter = cls(manager, server_name=server_name)
        
        print(f"Starting MCP Server '{server_name}' with storage at {os.path.abspath(storage_path)}...")
        adapter.run()
