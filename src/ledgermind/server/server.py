import logging
from typing import Any, Dict, List, Optional
import json
import os
import enum
import httpx
import asyncio
import time
import threading
from mcp.server.fastmcp import FastMCP
from prometheus_client import start_http_server, Counter, Histogram
from ledgermind.core.api.memory import Memory
from ledgermind.server.tools.environment import EnvironmentContext
from ledgermind.server.audit import AuditLogger
from ledgermind.server.contracts import (
    RecordDecisionRequest, SupersedeDecisionRequest, 
    SearchDecisionsRequest, AcceptProposalRequest,
    DecisionResponse, SearchResponse, BaseResponse, SyncGitResponse,
    MCP_API_VERSION
)

logger = logging.getLogger("ledgermind.server")

# Metrics definitions
TOOL_CALLS = Counter("agent_memory_tool_calls_total", "Total number of tool calls", ["tool", "status"])
TOOL_LATENCY = Histogram("agent_memory_tool_latency_seconds", "Latency of tool calls in seconds", ["tool"])

class MCPRole(str, enum.Enum):
    VIEWER = "viewer"
    AGENT = "agent"
    ADMIN = "admin"

class MCPServer:
    current_instance = None

    def __init__(self, 
                 memory: Memory, 
                 server_name: str = "Ledgermind", 
                 storage_path: str = ".ledgermind",
                 capabilities: Optional[Dict[str, bool]] = None,
                 metrics_port: Optional[int] = None,
                 rest_port: Optional[int] = None,
                 default_role: MCPRole = MCPRole.AGENT,
                 start_worker: bool = True,
                 webhooks: Optional[List[str]] = None):

        self.memory = memory
        self.default_role = default_role
        self.capabilities = capabilities if capabilities is not None else {
            "read": True, "propose": True, "supersede": True, 
            "accept": True, "sync": True, "purge": False
        }
        self.metrics_port = metrics_port
        self.rest_port = rest_port
        self.webhooks = webhooks or []

        self.mcp = FastMCP(f"{server_name} (v{MCP_API_VERSION})")

        self.env_context = EnvironmentContext(memory)
        self.audit_logger = AuditLogger(storage_path)
        
        # Security Configuration
        self.api_key = os.environ.get("LEDGERMIND_API_KEY")
        if self.api_key:
            logger.info("API Key authentication enabled.")
        
        self._last_write_time = 0
        self._write_cooldown = 1.0 
        self._register_tools()
        
        # Subscribe to events for webhooks
        if self.webhooks:
            from ledgermind.core.api.memory import Memory
            # Memory class has an 'events' object (EventEmitter)
            # Need to make sure it's accessible.
            if hasattr(self.memory, 'events'):
                self.memory.events.subscribe(self._trigger_webhooks)

        # Initialize Background Worker (Active Loop)
        from ledgermind.server.background import BackgroundWorker
        self.worker = BackgroundWorker(self.memory)
        if start_worker:
            self.worker.start()

    def _trigger_webhooks(self, event_type: str, data: Any):
        """Dispatches event to all registered webhook URLs."""
        if not self.webhooks: return
        
        async def _notify():
            async with httpx.AsyncClient() as client:
                payload = {"event": event_type, "data": data, "timestamp": time.time()}
                tasks = [client.post(url, json=payload, timeout=2.0) for url in self.webhooks]
                await asyncio.gather(*tasks, return_exceptions=True)
        
        # Run in background to avoid blocking main thread
        asyncio.create_task(_notify())

    def _validate_auth(self):
        """Validates the request against the configured API key."""
        if not self.api_key:
            return
            
        # FastMCP context might not be directly accessible here easily 
        # for all transports, but we can attempt to check environment/session
        # In a real MCP scenario, this would check the request metadata.
        
        from mcp.server.fastmcp import Context
        ctx: Context = getattr(self.mcp, "context", None)
        
        # If we have request context (SSE/HTTP), check headers
        if ctx and hasattr(ctx, "request_context") and ctx.request_context:
            headers = getattr(ctx.request_context.request, "headers", {})
            provided_key = headers.get("X-API-Key") or headers.get("x-api-key")
            if provided_key != self.api_key:
                raise PermissionError("Invalid or missing X-API-Key header.")
        
        # For stdio, we assume the environment is already secured or the key 
        # is passed via transport-specific metadata if supported by the client.
        # Currently, if LEDGERMIND_API_KEY is set but no header is found in SSE, it fails.

    def _validate_isolation(self, decision_ids: List[str]):
        """
        Enforces that agents can only supersede decisions created via MCP.
        Human-created decisions are protected.
        """
        if self.default_role != MCPRole.ADMIN:
            for d_id in decision_ids:
                path = os.path.join(self.memory.semantic.repo_path, d_id)
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        content = f.read()
                        if "[via MCP]" not in content:
                            raise PermissionError(f"Isolation Violation: Decision {d_id} was created by a human and cannot be modified by an agent.")

    def _check_capability(self, capability: str):
        if not self.capabilities.get(capability, False):
            raise PermissionError(f"Capability '{capability}' is required for this operation.")

    def _apply_cooldown(self):
        import time
        now = time.time()
        if now - self._last_write_time < self._write_cooldown:
            raise PermissionError(f"Rate limit exceeded: please wait {self._write_cooldown}s between operations.")
        self._last_write_time = now

    # --- Tool Handlers ---

    def _get_commit_hash(self) -> Optional[str]:
        return self.memory.semantic.get_head_hash()

    def handle_record_decision(self, request: RecordDecisionRequest) -> DecisionResponse:
        start_time = time.time()
        try:
            self._validate_auth()
            self._check_capability("propose")
            self._apply_cooldown()
            result = self.memory.record_decision(
                title=request.title, 
                target=request.target,
                rationale=f"[via MCP] {request.rationale}",
                consequences=request.consequences,
                namespace=request.namespace
            )
            dec_id = result.metadata.get("file_id")
            commit_hash = self._get_commit_hash()
            self.audit_logger.log_access("agent", "record_decision", request.model_dump(), True, commit_hash=commit_hash)
            TOOL_CALLS.labels(tool="record_decision", status="success").inc()
            return DecisionResponse(status="success", decision_id=dec_id)
        except Exception as e:
            self.audit_logger.log_access("agent", "record_decision", request.model_dump(), False, error=str(e))
            TOOL_CALLS.labels(tool="record_decision", status="error").inc()
            return DecisionResponse(status="error", message=str(e))
        finally:
            TOOL_LATENCY.labels(tool="record_decision").observe(time.time() - start_time)

    def handle_supersede_decision(self, request: SupersedeDecisionRequest) -> DecisionResponse:
        start_time = time.time()
        try:
            self._validate_auth()
            self._check_capability("supersede")
            self._validate_isolation(request.old_decision_ids)
            result = self.memory.supersede_decision(
                title=request.title, target=request.target,
                rationale=f"[via MCP] {request.rationale}",
                old_decision_ids=request.old_decision_ids,
                consequences=request.consequences,
                namespace=request.namespace
            )
            dec_id = result.metadata.get("file_id")
            commit_hash = self._get_commit_hash()
            self.audit_logger.log_access("agent", "supersede_decision", request.model_dump(), True, commit_hash=commit_hash)
            TOOL_CALLS.labels(tool="supersede_decision", status="success").inc()
            return DecisionResponse(status="success", decision_id=dec_id)
        except Exception as e:
            self.audit_logger.log_access("agent", "supersede_decision", request.model_dump(), False, error=str(e))
            TOOL_CALLS.labels(tool="supersede_decision", status="error").inc()
            return DecisionResponse(status="error", message=str(e))
        finally:
            TOOL_LATENCY.labels(tool="supersede_decision").observe(time.time() - start_time)

    def handle_search(self, request: SearchDecisionsRequest) -> SearchResponse:
        start_time = time.time()
        try:
            self._validate_auth()
            self._check_capability("read")
            results = self.memory.search_decisions(
                request.query, 
                limit=request.limit, 
                offset=request.offset,
                namespace=request.namespace,
                mode=request.mode
            )
            self.audit_logger.log_access("agent", "search_decisions", request.model_dump(), True)
            TOOL_CALLS.labels(tool="search_decisions", status="success").inc()
            return SearchResponse(status="success", results=results)
        except Exception as e:
            self.audit_logger.log_access("agent", "search_decisions", request.model_dump(), False, error=str(e))
            TOOL_CALLS.labels(tool="search_decisions", status="error").inc()
            return SearchResponse(status="error", message=str(e))
        finally:
            TOOL_LATENCY.labels(tool="search_decisions").observe(time.time() - start_time)

    def handle_accept_proposal(self, request: AcceptProposalRequest) -> BaseResponse:
        start_time = time.time()
        try:
            self._check_capability("accept")
            self.memory.accept_proposal(request.proposal_id)
            commit_hash = self._get_commit_hash()
            self.audit_logger.log_access("agent", "accept_proposal", request.model_dump(), True, commit_hash=commit_hash)
            TOOL_CALLS.labels(tool="accept_proposal", status="success").inc()
            return BaseResponse(status="success", message="Accepted")
        except Exception as e:
            self.audit_logger.log_access("agent", "accept_proposal", request.model_dump(), False, error=str(e))
            TOOL_CALLS.labels(tool="accept_proposal", status="error").inc()
            return BaseResponse(status="error", message=str(e))
        finally:
            TOOL_LATENCY.labels(tool="accept_proposal").observe(time.time() - start_time)

    def _register_tools(self):
        """
        Регистрация инструментов. FastMCP автоматически использует аннотации типов 
        Pydantic моделей для генерации JSON-схем инструментов.
        """
        @self.mcp.tool()
        def record_decision(title: str, target: str, rationale: str, consequences: Optional[List[str]] = None, namespace: str = "default") -> str:
            """Records a strategic decision into semantic memory."""
            req = RecordDecisionRequest(title=title, target=target, rationale=rationale, consequences=consequences or [], namespace=namespace)
            return self.handle_record_decision(req).model_dump_json()

        @self.mcp.tool()
        def supersede_decision(title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None, namespace: str = "default") -> str:
            """Replaces old decisions with a new one."""
            req = SupersedeDecisionRequest(title=title, target=target, rationale=rationale, old_decision_ids=old_decision_ids, consequences=consequences or [], namespace=namespace)
            return self.handle_supersede_decision(req).model_dump_json()

        @self.mcp.tool()
        def search_decisions(query: str, limit: int = 5, offset: int = 0, namespace: str = "default", mode: str = "balanced") -> str:
            """Keyword search for active decisions and rules. Mode can be 'strict', 'balanced', or 'audit'."""
            req = SearchDecisionsRequest(query=query, limit=limit, offset=offset, namespace=namespace, mode=mode)
            return self.handle_search(req).model_dump_json()

        @self.mcp.tool()
        def accept_proposal(proposal_id: str) -> str:
            """Converts a draft proposal into an active decision."""
            req = AcceptProposalRequest(proposal_id=proposal_id)
            return self.handle_accept_proposal(req).model_dump_json()

        @self.mcp.tool()
        def sync_git_history(repo_path: str = ".", limit: int = 20) -> str:
            """Syncs Git commit history into episodic memory."""
            start_time = time.time()
            try:
                self._check_capability("sync")
                count = self.memory.sync_git(repo_path=repo_path, limit=limit)
                self.audit_logger.log_access("agent", "sync_git_history", {"repo_path": repo_path, "limit": limit}, True)
                TOOL_CALLS.labels(tool="sync_git_history", status="success").inc()
                return SyncGitResponse(status="success", indexed_commits=count).model_dump_json()
            except Exception as e:
                self.audit_logger.log_access("agent", "sync_git_history", {"repo_path": repo_path, "limit": limit}, False, error=str(e))
                TOOL_CALLS.labels(tool="sync_git_history", status="error").inc()
                return json.dumps({"status": "error", "message": str(e)})
            finally:
                TOOL_LATENCY.labels(tool="sync_git_history").observe(time.time() - start_time)

        @self.mcp.tool()
        def forget_memory(decision_id: str) -> str:
            """Hard-deletes a memory from filesystem and metadata (GDPR purge)."""
            start_time = time.time()
            try:
                self._check_capability("purge")
                self.memory.forget(decision_id)
                self.audit_logger.log_access("admin", "forget_memory", {"id": decision_id}, True)
                TOOL_CALLS.labels(tool="forget_memory", status="success").inc()
                return json.dumps({"status": "success", "message": f"Forgotten {decision_id}"})
            except Exception as e:
                self.audit_logger.log_access("admin", "forget_memory", {"id": decision_id}, False, error=str(e))
                TOOL_CALLS.labels(tool="forget_memory", status="error").inc()
                return json.dumps({"status": "error", "message": str(e)})
            finally:
                TOOL_LATENCY.labels(tool="forget_memory").observe(time.time() - start_time)

        @self.mcp.tool()
        def visualize_graph(target: Optional[str] = None) -> str:
            """Generates a Mermaid diagram of the knowledge evolution graph. Optional 'target' to filter."""
            start_time = time.time()
            try:
                self._check_capability("read")
                mermaid_code = self.memory.generate_knowledge_graph(target=target)
                self.audit_logger.log_access("agent", "visualize_graph", {"target": target}, True)
                TOOL_CALLS.labels(tool="visualize_graph", status="success").inc()
                return json.dumps({"status": "success", "mermaid": mermaid_code})
            except Exception as e:
                self.audit_logger.log_access("agent", "visualize_graph", {"target": target}, False, error=str(e))
                TOOL_CALLS.labels(tool="visualize_graph", status="error").inc()
                return json.dumps({"status": "error", "message": str(e)})
            finally:
                TOOL_LATENCY.labels(tool="visualize_graph").observe(time.time() - start_time)

        @self.mcp.tool()
        def get_memory_stats() -> str:
            """Returns memory usage statistics."""
            start_time = time.time()
            try:
                self._check_capability("read")
                stats = self.memory.get_stats()
                self.audit_logger.log_access("agent", "get_memory_stats", {}, True)
                TOOL_CALLS.labels(tool="get_memory_stats", status="success").inc()
                return json.dumps({"status": "success", "stats": stats})
            except Exception as e:
                self.audit_logger.log_access("agent", "get_memory_stats", {}, False, error=str(e))
                TOOL_CALLS.labels(tool="get_memory_stats", status="error").inc()
                return json.dumps({"status": "error", "message": str(e)})
            finally:
                TOOL_LATENCY.labels(tool="get_memory_stats").observe(time.time() - start_time)

        @self.mcp.tool()
        def get_environment_health() -> str:
            """Returns diagnostic information about the system environment (disk, git, python)."""
            start_time = time.time()
            try:
                self._check_capability("read")
                health = self.env_context.get_context()
                TOOL_CALLS.labels(tool="get_environment_health", status="success").inc()
                return json.dumps({"status": "success", "health": health})
            except Exception as e:
                TOOL_CALLS.labels(tool="get_environment_health", status="error").inc()
                return json.dumps({"status": "error", "message": str(e)})
            finally:
                TOOL_LATENCY.labels(tool="get_environment_health").observe(time.time() - start_time)

        @self.mcp.tool()
        def get_audit_logs(limit: int = 20) -> str:
            """Returns the last N lines of the MCP audit log."""
            start_time = time.time()
            try:
                self._check_capability("read")
                logs = self.audit_logger.get_logs(limit=limit)
                return json.dumps({"status": "success", "logs": logs})
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})
            finally:
                TOOL_LATENCY.labels(tool="get_audit_logs").observe(time.time() - start_time)

        @self.mcp.tool()
        def export_memory_bundle(output_filename: str = "memory_export.tar.gz") -> str:
            """Creates a full backup of the memory storage in a .tar.gz file."""
            start_time = time.time()
            try:
                self._check_capability("purge") # Exporting full data is a sensitive operation
                from ledgermind.core.api.transfer import MemoryTransferManager
                transfer = MemoryTransferManager(self.memory.storage_path)
                # Save to a temporary file in the same directory or specified path
                path = transfer.export_to_tar(output_filename)
                return json.dumps({"status": "success", "export_path": os.path.abspath(path)})
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})
            finally:
                TOOL_LATENCY.labels(tool="export_memory_bundle").observe(time.time() - start_time)

        @self.mcp.tool()
        def get_api_specification() -> str:
            """Returns the formal JSON specification (OpenRPC-like) of the Ledgermind API."""
            from ledgermind.server.specification import MCPApiSpecification
            spec = MCPApiSpecification.generate_full_spec()
            return json.dumps(spec, indent=2)

        @self.mcp.tool()
        def get_relevant_context(prompt: str, limit: int = 3) -> str:
            """Retrieves and formats relevant context for a given user prompt (Bridge Tool)."""
            from ledgermind.core.api.bridge import IntegrationBridge
            bridge = IntegrationBridge(memory_path=self.memory.storage_path)
            return bridge.get_context_for_prompt(prompt, limit=limit)

        @self.mcp.tool()
        def record_interaction(prompt: str, response: str, success: bool = True) -> str:
            """Records a completed interaction (prompt and response) into episodic memory (Bridge Tool)."""
            from ledgermind.core.api.bridge import IntegrationBridge
            bridge = IntegrationBridge(memory_path=self.memory.storage_path)
            bridge.record_interaction(prompt, response, success=success)
            return json.dumps({"status": "success"})

        @self.mcp.tool()
        def link_interaction_to_decision(event_id: int, decision_id: str) -> str:
            """Links a specific episodic event (e.g., from search) to a semantic decision as evidence."""
            start_time = time.time()
            try:
                self._check_capability("supersede")
                self.memory.link_evidence(event_id, decision_id)
                return json.dumps({"status": "success", "message": f"Linked event {event_id} to {decision_id}"})
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})
            finally:
                TOOL_LATENCY.labels(tool="link_interaction_to_decision").observe(time.time() - start_time)

    def stop(self):
        """Gracefully shuts down the server and all background processes."""
        logger.info("Shutting down MCPServer...")
        if hasattr(self, 'worker'):
            self.worker.stop()
        
        if hasattr(self.memory, 'vector'):
            self.memory.vector.close()
            
        logger.info("MCPServer shutdown complete.")

    def run(self):
        if self.metrics_port:
            logger.info(f"Starting Prometheus metrics server on port {self.metrics_port}")
            start_http_server(self.metrics_port)
        
        if self.rest_port:
            logger.info(f"Starting REST Gateway on port {self.rest_port}")
            from ledgermind.server.gateway import run_gateway
            import threading
            gateway_thread = threading.Thread(
                target=run_gateway, 
                args=(self.memory,), 
                kwargs={"port": self.rest_port},
                daemon=True
            )
            gateway_thread.start()
            
        self.mcp.run()


    @classmethod
    def serve(cls, 
              storage_path: str = ".ledgermind", 
              server_name: str = "Ledgermind",
              capabilities: Optional[Dict[str, bool]] = None,
              metrics_port: Optional[int] = None,
              rest_port: Optional[int] = None,
              vector_workers: int = 0):
        from ledgermind.core.core.schemas import TrustBoundary
        
        memory = Memory(storage_path=storage_path, trust_boundary=TrustBoundary.AGENT_WITH_INTENT, vector_workers=vector_workers)
        server = cls(
            memory, 
            server_name=server_name, 
            storage_path=storage_path,
            capabilities=capabilities,
            metrics_port=metrics_port,
            rest_port=rest_port
        )
        server.run()

