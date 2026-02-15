from typing import Any, Dict, List, Optional
import json
import os
from mcp.server.fastmcp import FastMCP
from agent_memory_core.api.memory import Memory
from agent_memory_server.tools.environment import EnvironmentContext

class MCPServer:
    """
    Dedicated MCP Server for agent-memory-core.
    Acts as the primary enforcement layer and transport for memory operations.
    """

    def __init__(self, memory: Memory, server_name: str = "AgentMemory"):
        self.memory = memory
        self.mcp = FastMCP(server_name)
        self.env_context = EnvironmentContext(memory)
        self._register_tools()

    def _register_tools(self):
        @self.mcp.tool()
        def record_decision(title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> str:
            """Records a strategic decision into semantic memory."""
            if len(rationale.strip()) < 10:
                return json.dumps({"status": "error", "message": "Rationale too short (min 10 chars)"})

            result = self.memory.record_decision(
                title=title,
                target=target,
                rationale=f"[via MCP] {rationale}",
                consequences=consequences or []
            )
            return json.dumps({
                "status": "success", 
                "decision_id": result.metadata.get("file_id", "unknown"),
                "message": "Decision recorded"
            }, ensure_ascii=False)

        @self.mcp.tool()
        def supersede_decision(title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> str:
            """Replaces old decisions with a new one."""
            if len(rationale.strip()) < 15:
                return json.dumps({"status": "error", "message": "Rationale too short for supersede (min 15 chars)"})

            try:
                result = self.memory.supersede_decision(
                    title=title,
                    target=target,
                    rationale=f"[via MCP] {rationale}",
                    old_decision_ids=old_decision_ids,
                    consequences=consequences or []
                )
                return json.dumps({
                    "status": "success", 
                    "decision_id": result.metadata.get("file_id", "unknown"),
                    "message": "Decision superseded"
                }, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

        @self.mcp.tool()
        def search_decisions(query: str, limit: int = 5) -> str:
            """Semantic search for active decisions and rules."""
            results = self.memory.search_decisions(query, limit=limit)
            return json.dumps({"status": "success", "results": results}, ensure_ascii=False)

        @self.mcp.tool()
        def capture_context(label: str = "general_context") -> str:
            """Captures environment snapshot (files, git) to episodic memory."""
            result = self.env_context.capture_context(label=label)
            return json.dumps(result, ensure_ascii=False)

        @self.mcp.tool()
        def sync_git_history(repo_path: str = ".", limit: int = 20) -> str:
            """Syncs Git commit history into episodic memory for reflection."""
            count = self.memory.sync_git(repo_path=repo_path, limit=limit)
            return json.dumps({"status": "success", "indexed_commits": count}, ensure_ascii=False)

        @self.mcp.tool()
        def accept_proposal(proposal_id: str) -> str:
            """Converts a draft proposal into an active decision."""
            try:
                result = self.memory.accept_proposal(proposal_id)
                return json.dumps({"status": "success", "message": "Proposal accepted", "decision_id": result.metadata.get("file_id")}, ensure_ascii=False)
            except PermissionError as e:
                return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"status": "error", "message": f"Error: {str(e)}"}, ensure_ascii=False)

    def run(self):
        self.mcp.run()

    @classmethod
    def serve(cls, storage_path: str = ".agent_memory", server_name: str = "AgentMemory"):
        from agent_memory_core.embeddings import MockEmbeddingProvider # Temporarily use mock if none provided
        
        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)

        memory = Memory(storage_path=storage_path, embedding_provider=MockEmbeddingProvider())
        server = cls(memory, server_name=server_name)
        server.run()
