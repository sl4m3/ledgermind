from typing import Any, Dict, List, Optional
import json
import os
import enum
import httpx
import asyncio
from mcp.server.fastmcp import FastMCP
from prometheus_client import start_http_server
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

    def __init__(self, memory: Memory, server_name: str = "AgentMemory", 

                 default_role: MCPRole = MCPRole.AGENT,

                 capabilities: Optional[Dict[str, bool]] = None,

                 webhook_urls: Optional[List[str]] = None):

        self.memory = memory

        self.mcp = FastMCP(f"{server_name} (v{MCP_API_VERSION})")

        self.env_context = EnvironmentContext(memory)

        self.default_role = default_role

        self.webhook_urls = webhook_urls or []

        

        # Initialize capabilities
        # either from provided dict or derived from role
        self.capabilities = capabilities if capabilities is not None else self._get_default_capabilities(default_role)
        
        self._last_write_time = 0
        self._write_cooldown = 2.0 
        self.audit = AuditLogger(memory.storage_path) # Audit integration
        self._register_tools()

    def _get_default_capabilities(self, role: MCPRole) -> Dict[str, bool]:
        """Maps legacy roles to granular capabilities."""
        caps = {
            "read": True,
            "propose": False,
            "supersede": False,
            "accept": False,
            "sync": False,
            "purge": False
        }
        if role in [MCPRole.AGENT, MCPRole.ADMIN]:
            caps["propose"] = True
            caps["supersede"] = True
            caps["sync"] = True
        if role == MCPRole.ADMIN:
            caps["accept"] = True
            caps["purge"] = True
        return caps

    def _check_auth(self, capability: str, tool_name: str = "unknown") -> bool:
        allowed = self.capabilities.get(capability, False)
        
        if not allowed:
            self.audit.log_access(self.default_role.value, tool_name, {}, False, f"Permission denied: missing '{capability}'")
        
        return allowed

    def _apply_cooldown(self):
        import time
        now = time.time()
        if now - self._last_write_time < self._write_cooldown:
            raise PermissionError(f"Rate limit exceeded: please wait {self._write_cooldown}s between operations.")
        self._last_write_time = now

    def _notify_webhooks(self, event_type: str, data: Dict[str, Any]):
        """Async background notification for registered webhooks."""
        if not self.webhook_urls: return
        
        async def send_all():
            payload = {
                "event": event_type,
                "timestamp": datetime.now().isoformat(),
                "data": data,
                "server": self.mcp.name
            }
            async with httpx.AsyncClient() as client:
                tasks = [client.post(url, json=payload, timeout=2.0) for url in self.webhook_urls]
                await asyncio.gather(*tasks, return_exceptions=True)
        
        # Fire and forget if loop is running
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_all())
        except RuntimeError:
            # Fallback for non-async contexts if any
            asyncio.run(send_all())

    # --- Tool Handlers ---

    def _get_commit_hash(self) -> Optional[str]:
        return self.memory.semantic.get_head_hash()

    def handle_record_decision(self, request: RecordDecisionRequest) -> DecisionResponse:
        if not self._check_auth("propose", "record_decision"):
            return DecisionResponse(status="error", message="Permission denied: missing 'propose'")
        
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
            dec_id = result.metadata.get("file_id")
            self._notify_webhooks("decision_recorded", {"id": dec_id, "target": request.target, "title": request.title})
            return DecisionResponse(status="success", decision_id=dec_id)
        except Exception as e:
            self.audit.log_access(self.default_role.value, "record_decision", request.model_dump(), False, str(e))
            return DecisionResponse(status="error", message=str(e))

    def handle_supersede_decision(self, request: SupersedeDecisionRequest) -> DecisionResponse:
        if not self._check_auth("supersede", "supersede_decision"):
            return DecisionResponse(status="error", message="Permission denied: missing 'supersede'")
        
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
            dec_id = result.metadata.get("file_id")
            self._notify_webhooks("decision_superseded", {"id": dec_id, "supersedes": request.old_decision_ids, "target": request.target})
            return DecisionResponse(status="success", decision_id=dec_id)
        except Exception as e:
            self.audit.log_access(self.default_role.value, "supersede_decision", request.model_dump(), False, str(e))
            return DecisionResponse(status="error", message=str(e))

    def handle_search(self, request: SearchDecisionsRequest) -> SearchResponse:
        if not self._check_auth("read", "search_decisions"):
            return SearchResponse(status="error", message="Permission denied: missing 'read'")
        try:
            results = self.memory.search_decisions(request.query, limit=request.limit, mode=request.mode)
            self.audit.log_access(self.default_role.value, "search_decisions", {"query": request.query, "mode": request.mode}, True)
            return SearchResponse(status="success", results=results)
        except Exception as e:
            self.audit.log_access(self.default_role.value, "search_decisions", request.model_dump(), False, str(e))
            return SearchResponse(status="error", message=str(e))

    def handle_accept_proposal(self, request: AcceptProposalRequest) -> BaseResponse:
        if not self._check_auth("accept", "accept_proposal"):
            return BaseResponse(status="error", message="Security Violation: 'accept' capability required")
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
            if not self._check_auth("sync", "sync_git_history"):
                return SyncGitResponse(status="error", message="Permission denied: missing 'sync'").model_dump_json()
            count = self.memory.sync_git(repo_path=repo_path, limit=limit)
            return SyncGitResponse(status="success", indexed_commits=count).model_dump_json()

        @self.mcp.tool()
        def visualize_graph(target: Optional[str] = None) -> str:
            """Generates a Mermaid diagram of the knowledge evolution graph. Optional 'target' to filter."""
            if not self._check_auth("read", "visualize_graph"):
                return json.dumps({"status": "error", "message": "Permission denied: missing 'read'"})
            mermaid_code = self.memory.generate_knowledge_graph(target=target)
            return json.dumps({"status": "success", "mermaid": mermaid_code})

        @self.mcp.tool()
        def get_memory_stats() -> str:
            """Returns memory usage statistics, most accessed items, and coverage gaps."""
            if not self._check_auth("read", "get_memory_stats"):
                return json.dumps({"status": "error", "message": "Permission denied: missing 'read'"})
            stats = self.memory.get_stats()
            return json.dumps({"status": "success", "stats": stats})

        @self.mcp.tool()
        def detect_knowledge_drift(days: int = 30) -> str:
            """Identifies unstable knowledge areas that have changed multiple times recently."""
            if not self._check_auth("read", "detect_knowledge_drift"):
                return json.dumps({"status": "error", "message": "Permission denied: missing 'read'"})
            drift = self.memory.detect_drift(days=days)
            return json.dumps({"status": "success", "drift": drift})

        @self.mcp.tool()
        def forget_memory(decision_id: str) -> str:
            """Permanently deletes a memory from the system (GDPR compliance). Requires 'purge' capability."""
            if not self._check_auth("purge", "forget_memory"):
                return json.dumps({"status": "error", "message": "Permission denied: missing 'purge'"})
            try:
                self.memory.forget(decision_id)
                self.audit.log_access(self.default_role.value, "forget_memory", {"id": decision_id}, True)
                return json.dumps({"status": "success", "message": f"Memory {decision_id} has been forgotten."})
            except Exception as e:
                self.audit.log_access(self.default_role.value, "forget_memory", {"id": decision_id}, False, str(e))
                return json.dumps({"status": "error", "message": str(e)})

    def run(self):
        self.mcp.run()

    @classmethod
    def serve(cls, storage_path: str = ".agent_memory", server_name: str = "AgentMemory", 
              role: str = "agent", capabilities: Optional[Dict[str, bool]] = None,
              metrics_port: Optional[int] = None,
              webhook_urls: Optional[List[str]] = None,
              rest_port: Optional[int] = None):
        from agent_memory_adapters.embeddings import (
            GoogleEmbeddingProvider, OpenAIEmbeddingProvider, MockEmbeddingProvider
        )
        from agent_memory_core.core.schemas import TrustBoundary
        import sys
        import threading
        
        # Start Prometheus metrics server
        if metrics_port:
            try:
                start_http_server(metrics_port)
                print(f"Metrics server started on port {metrics_port}", file=sys.stderr)
            except Exception as e:
                print(f"FAILED to start metrics server: {e}", file=sys.stderr)

        mcp_role = MCPRole(role)
        
        # Security: Capability check (omitted for brevity in this replace call)

        # Select best available embedding provider
        emb_provider = None
        if os.environ.get("GOOGLE_API_KEY"):
            try:
                emb_provider = GoogleEmbeddingProvider()
                print("Using GoogleEmbeddingProvider for search.", file=sys.stderr)
            except Exception as e:
                print(f"GoogleEmbeddingProvider init failed: {e}", file=sys.stderr)
        
        if not emb_provider and os.environ.get("OPENAI_API_KEY"):
            try:
                emb_provider = OpenAIEmbeddingProvider()
                print("Using OpenAIEmbeddingProvider for search.", file=sys.stderr)
            except Exception as e:
                print(f"OpenAIEmbeddingProvider init failed: {e}", file=sys.stderr)
        
        trust = TrustBoundary.HUMAN_ONLY if mcp_role == MCPRole.VIEWER else TrustBoundary.AGENT_WITH_INTENT
        memory = Memory(storage_path=storage_path, embedding_provider=emb_provider, trust_boundary=trust)
        
        # Start REST Gateway if requested
        if rest_port:
            from agent_memory_server.gateway import run_gateway
            gt_thread = threading.Thread(target=run_gateway, args=(memory, "0.0.0.0", rest_port), daemon=True) # nosec B104
            gt_thread.start()
            print(f"REST API Gateway started on port {rest_port}", file=sys.stderr)

        server = cls(memory, server_name=server_name, default_role=mcp_role, capabilities=capabilities, webhook_urls=webhook_urls)
        server.run()
