from typing import Any, Dict, List, Optional
import json
import os
import enum
from mcp.server.fastmcp import FastMCP
from agent_memory_core.api.memory import Memory
from agent_memory_server.tools.environment import EnvironmentContext
from agent_memory_server.audit import AuditLogger
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
        self.mcp = FastMCP(f"{server_name} (v{MCP_API_VERSION})")
        self.env_context = EnvironmentContext(memory)
        self.default_role = default_role
        
        # Hardened Security Check: Enforce secret presence for privileged roles at instantiation
        if self.default_role in [MCPRole.AGENT, MCPRole.ADMIN]:
            if not os.environ.get("AGENT_MEMORY_SECRET"):
                # Downgrade immediately if secret is missing to fail safe
                # print("SECURITY WARNING: Downgrading to VIEWER due to missing secret.")
                self.default_role = MCPRole.VIEWER
        
        self._last_write_time = 0
        self._write_cooldown = 2.0 
        self.audit = AuditLogger(memory.storage_path) # Audit integration
        self._register_tools()

    def _check_auth(self, required_role: MCPRole, tool_name: str = "unknown") -> bool:
        role_hierarchy = {MCPRole.VIEWER: 0, MCPRole.AGENT: 1, MCPRole.ADMIN: 2}
        allowed = role_hierarchy.get(self.default_role, 0) >= role_hierarchy.get(required_role, 0)
        
        if not allowed:
            self.audit.log_access(self.default_role.value, tool_name, {}, False, "Permission denied")
        
        return allowed

    def _apply_cooldown(self):
        import time
        now = time.time()
        if now - self._last_write_time < self._write_cooldown:
            raise PermissionError(f"Rate limit exceeded: please wait {self._write_cooldown}s between operations.")
        self._last_write_time = now

    # --- Tool Handlers with Contract Validation ---

    def _get_commit_hash(self) -> Optional[str]:
        return self.memory.semantic.get_head_hash()

    def handle_record_decision(self, request: RecordDecisionRequest) -> DecisionResponse:
        if not self._check_auth(MCPRole.AGENT, "record_decision"):
            return DecisionResponse(status="error", message="Permission denied")
        
        try:
            self._apply_cooldown()
            result = self.memory.record_decision(
                title=request.title, 
                target=request.target,
                rationale=f"[via MCP:{self.default_role.value}] {request.rationale}",
                consequences=request.consequences
            )
            commit_hash = self._get_commit_hash()
            self.audit.log_access(self.default_role.value, "record_decision", request.model_dump(), True, commit_hash=commit_hash)
            return DecisionResponse(status="success", decision_id=result.metadata.get("file_id"))
        except Exception as e:
            self.audit.log_access(self.default_role.value, "record_decision", request.model_dump(), False, str(e))
            return DecisionResponse(status="error", message=str(e))

    def handle_supersede_decision(self, request: SupersedeDecisionRequest) -> DecisionResponse:
        if not self._check_auth(MCPRole.AGENT, "supersede_decision"):
            return DecisionResponse(status="error", message="Permission denied")
        
        # Isolation Rule Enforcement
        if self.default_role == MCPRole.AGENT:
            for old_id in request.old_decision_ids:
                try:
                    file_path = os.path.join(self.memory.semantic.repo_path, old_id)
                    with open(file_path, 'r') as f:
                        if "[via MCP]" not in f.read():
                            err = f"Isolation Violation: Decision {old_id} created by HUMAN."
                            self.audit.log_access(self.default_role.value, "supersede_decision", request.model_dump(), False, err)
                            return DecisionResponse(status="error", message=err)
                except Exception: continue

        try:
            result = self.memory.supersede_decision(
                title=request.title, target=request.target,
                rationale=f"[via MCP:{self.default_role.value}] {request.rationale}",
                old_decision_ids=request.old_decision_ids,
                consequences=request.consequences
            )
            commit_hash = self._get_commit_hash()
            self.audit.log_access(self.default_role.value, "supersede_decision", request.model_dump(), True, commit_hash=commit_hash)
            return DecisionResponse(status="success", decision_id=result.metadata.get("file_id"))
        except Exception as e:
            self.audit.log_access(self.default_role.value, "supersede_decision", request.model_dump(), False, str(e))
            return DecisionResponse(status="error", message=str(e))

    def handle_search(self, request: SearchDecisionsRequest) -> SearchResponse:
        try:
            results = self.memory.search_decisions(request.query, limit=request.limit, mode=request.mode)
            self.audit.log_access(self.default_role.value, "search_decisions", {"query": request.query, "mode": request.mode}, True)
            return SearchResponse(status="success", results=results)
        except Exception as e:
            self.audit.log_access(self.default_role.value, "search_decisions", request.model_dump(), False, str(e))
            return SearchResponse(status="error", message=str(e))

    def handle_accept_proposal(self, request: AcceptProposalRequest) -> BaseResponse:
        if not self._check_auth(MCPRole.ADMIN, "accept_proposal"):
            return BaseResponse(status="error", message="Security Violation: ADMIN required")
        try:
            self.memory.accept_proposal(request.proposal_id)
            commit_hash = self._get_commit_hash()
            self.audit.log_access(self.default_role.value, "accept_proposal", request.model_dump(), True, commit_hash=commit_hash)
            return BaseResponse(status="success", message="Accepted")
        except Exception as e:
            self.audit.log_access(self.default_role.value, "accept_proposal", request.model_dump(), False, str(e))
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
        def search_decisions(query: str, limit: int = 5, mode: str = "balanced") -> str:
            """Semantic search for active decisions and rules. Mode can be 'strict', 'balanced', or 'audit'."""
            req = SearchDecisionsRequest(query=query, limit=limit, mode=mode)
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
        from agent_memory_adapters.embeddings import MockEmbeddingProvider
        from agent_memory_core.core.schemas import TrustBoundary
        import sys
        
        mcp_role = MCPRole(role)
        
        # Security Enforcement: Privileged roles require a secret token
        if mcp_role in [MCPRole.AGENT, MCPRole.ADMIN]:
            secret = os.environ.get("AGENT_MEMORY_SECRET")
            if not secret:
                print(f"SECURITY ERROR: Role '{role}' requires AGENT_MEMORY_SECRET environment variable to be set.", file=sys.stderr)
                print("Falling back to VIEWER role for safety.", file=sys.stderr)
                mcp_role = MCPRole.VIEWER
        
        trust = TrustBoundary.HUMAN_ONLY if mcp_role == MCPRole.VIEWER else TrustBoundary.AGENT_WITH_INTENT
        memory = Memory(storage_path=storage_path, embedding_provider=MockEmbeddingProvider(), trust_boundary=trust)
        server = cls(memory, server_name=server_name, default_role=mcp_role)
        server.run()
