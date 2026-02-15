from typing import Any, Dict, List, Optional
import json
import os
import enum
from mcp.server.fastmcp import FastMCP
from agent_memory_core.api.memory import Memory
from agent_memory_server.tools.environment import EnvironmentContext

class MCPRole(str, enum.Enum):
    VIEWER = "viewer"
    AGENT = "agent"
    ADMIN = "admin"

class MCPServer:
    def __init__(self, memory: Memory, server_name: str = "AgentMemory", default_role: MCPRole = MCPRole.AGENT):
        self.memory = memory
        self.mcp = FastMCP(server_name)
        self.env_context = EnvironmentContext(memory)
        self.default_role = default_role
        self._register_tools()

    def _check_auth(self, required_role: MCPRole) -> bool:
        role_hierarchy = {MCPRole.VIEWER: 0, MCPRole.AGENT: 1, MCPRole.ADMIN: 2}
        return role_hierarchy.get(self.default_role, 0) >= role_hierarchy.get(required_role, 0)

    # --- Tool Logic (Internal) ---

    def handle_record_decision(self, **kwargs) -> str:
        if not self._check_auth(MCPRole.AGENT):
            return json.dumps({"status": "error", "message": "Permission denied"})
        if len(kwargs.get('rationale', '').strip()) < 10:
            return json.dumps({"status": "error", "message": "Rationale too short"})
        
        result = self.memory.record_decision(
            title=kwargs['title'], target=kwargs['target'],
            rationale=f"[via MCP:{self.default_role.value}] {kwargs['rationale']}",
            consequences=kwargs.get('consequences', [])
        )
        return json.dumps({"status": "success", "decision_id": result.metadata.get("file_id")}, ensure_ascii=False)

    def handle_accept_proposal(self, proposal_id: str) -> str:
        if not self._check_auth(MCPRole.ADMIN):
            return json.dumps({"status": "error", "message": "Security Violation: ADMIN required"})
        try:
            result = self.memory.accept_proposal(proposal_id)
            return json.dumps({"status": "success", "message": "Accepted"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def _register_tools(self):
        @self.mcp.tool()
        def record_decision(title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> str:
            return self.handle_record_decision(title=title, target=target, rationale=rationale, consequences=consequences)

        @self.mcp.tool()
        def accept_proposal(proposal_id: str) -> str:
            return self.handle_accept_proposal(proposal_id)

        @self.mcp.tool()
        def search_decisions(query: str, limit: int = 5) -> str:
            results = self.memory.search_decisions(query, limit=limit)
            return json.dumps({"status": "success", "results": results}, ensure_ascii=False)

    def run(self):
        self.mcp.run()

    @classmethod
    def serve(cls, storage_path: str = ".agent_memory", server_name: str = "AgentMemory", role: str = "agent"):
        from agent_memory_core.embeddings import MockEmbeddingProvider
        from agent_memory_core.core.schemas import TrustBoundary
        mcp_role = MCPRole(role)
        trust = TrustBoundary.AGENT_WITH_INTENT if mcp_role != MCPRole.ADMIN else TrustBoundary.HUMAN_ONLY
        memory = Memory(storage_path=storage_path, embedding_provider=MockEmbeddingProvider(), trust_boundary=trust)
        server = cls(memory, server_name=server_name, default_role=mcp_role)
        server.run()
