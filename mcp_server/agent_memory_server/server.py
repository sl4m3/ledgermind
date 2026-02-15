from typing import Any, Dict, List, Optional
import json
import os
import enum
from mcp.server.fastmcp import FastMCP
from agent_memory_core.api.memory import Memory
from agent_memory_server.tools.environment import EnvironmentContext
from agent_memory_server.contracts import (
    RecordDecisionRequest, SupersedeDecisionRequest, 
    SearchDecisionsRequest, AcceptProposalRequest,
    DecisionResponse, SearchResponse, BaseResponse, SyncGitResponse,
    MCP_API_VERSION
)

class MCPRole(str, enum.Enum):
    VIEWER = "viewer"
    AGENT = "agent"
    ADMIN = "admin"

class MCPServer:
    def __init__(self, memory: Memory, server_name: str = "AgentMemory", default_role: MCPRole = MCPRole.AGENT):
        self.memory = memory
        # Добавляем версию API в название сервера для видимости клиентам
        self.mcp = FastMCP(f"{server_name} (v{MCP_API_VERSION})")
        self.env_context = EnvironmentContext(memory)
        self.default_role = default_role
        self._register_tools()

    def _check_auth(self, required_role: MCPRole) -> bool:
        role_hierarchy = {MCPRole.VIEWER: 0, MCPRole.AGENT: 1, MCPRole.ADMIN: 2}
        return role_hierarchy.get(self.default_role, 0) >= role_hierarchy.get(required_role, 0)

    # --- Tool Handlers with Contract Validation ---

    def handle_record_decision(self, request: RecordDecisionRequest) -> DecisionResponse:
        if not self._check_auth(MCPRole.AGENT):
            return DecisionResponse(status="error", message="Permission denied")
        
        try:
            result = self.memory.record_decision(
                title=request.title, 
                target=request.target,
                rationale=f"[via MCP:{self.default_role.value}] {request.rationale}",
                consequences=request.consequences
            )
            return DecisionResponse(status="success", decision_id=result.metadata.get("file_id"))
        except Exception as e:
            return DecisionResponse(status="error", message=str(e))

    def handle_supersede_decision(self, request: SupersedeDecisionRequest) -> DecisionResponse:
        if not self._check_auth(MCPRole.AGENT):
            return DecisionResponse(status="error", message="Permission denied")
        
        try:
            result = self.memory.supersede_decision(
                title=request.title, target=request.target,
                rationale=f"[via MCP:{self.default_role.value}] {request.rationale}",
                old_decision_ids=request.old_decision_ids,
                consequences=request.consequences
            )
            return DecisionResponse(status="success", decision_id=result.metadata.get("file_id"))
        except Exception as e:
            return DecisionResponse(status="error", message=str(e))

    def handle_search(self, request: SearchDecisionsRequest) -> SearchResponse:
        try:
            results = self.memory.search_decisions(request.query, limit=request.limit)
            return SearchResponse(status="success", results=results)
        except Exception as e:
            return SearchResponse(status="error", message=str(e))

    def handle_accept_proposal(self, request: AcceptProposalRequest) -> BaseResponse:
        if not self._check_auth(MCPRole.ADMIN):
            return BaseResponse(status="error", message="Security Violation: ADMIN required")
        try:
            self.memory.accept_proposal(request.proposal_id)
            return BaseResponse(status="success", message="Accepted")
        except Exception as e:
            return BaseResponse(status="error", message=str(e))

    def _register_tools(self):
        """
        Регистрация инструментов. FastMCP автоматически использует аннотации типов 
        Pydantic моделей для генерации JSON-схем инструментов.
        """
        @self.mcp.tool()
        def record_decision(title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> str:
            """Records a strategic decision into semantic memory."""
            req = RecordDecisionRequest(title=title, target=target, rationale=rationale, consequences=consequences or [])
            return self.handle_record_decision(req).model_dump_json()

        @self.mcp.tool()
        def supersede_decision(title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> str:
            """Replaces old decisions with a new one."""
            req = SupersedeDecisionRequest(title=title, target=target, rationale=rationale, old_decision_ids=old_decision_ids, consequences=consequences or [])
            return self.handle_supersede_decision(req).model_dump_json()

        @self.mcp.tool()
        def search_decisions(query: str, limit: int = 5) -> str:
            """Semantic search for active decisions and rules."""
            req = SearchDecisionsRequest(query=query, limit=limit)
            return self.handle_search(req).model_dump_json()

        @self.mcp.tool()
        def accept_proposal(proposal_id: str) -> str:
            """Converts a draft proposal into an active decision."""
            req = AcceptProposalRequest(proposal_id=proposal_id)
            return self.handle_accept_proposal(req).model_dump_json()

        @self.mcp.tool()
        def sync_git_history(repo_path: str = ".", limit: int = 20) -> str:
            """Syncs Git commit history into episodic memory."""
            count = self.memory.sync_git(repo_path=repo_path, limit=limit)
            return SyncGitResponse(status="success", indexed_commits=count).model_dump_json()

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
