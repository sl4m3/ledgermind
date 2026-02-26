import logging
from typing import Any, Dict, List, Optional
import os
import enum
import httpx
import asyncio
import time
import threading
import functools
import inspect
from mcp.server.fastmcp import FastMCP, Context
from prometheus_client import start_http_server, Counter, Histogram
from ledgermind.core.api.memory import Memory
from ledgermind.server.tools.environment import EnvironmentContext
from ledgermind.server.audit import AuditLogger
from ledgermind.server.contracts import (
    RecordDecisionRequest, SupersedeDecisionRequest, 
    SearchDecisionsRequest, AcceptProposalRequest,
    DecisionResponse, SearchResponse, BaseResponse, MCP_API_VERSION
)
from ledgermind.server.metrics import TOOL_CALLS, TOOL_LATENCY
from ledgermind.server.tools.definitions import LedgerMindTools

logger = logging.getLogger("ledgermind.server")

# Metrics definitions (in case they are not in ledgermind.server.metrics yet or for redundancy)
# But they ARE in origin/main so I'll keep them as they were in origin/main if they were added there.
# Looking at the conflict, they were added to server.py in origin/main.

def measure_and_log(tool_name: str, role: str = "agent", include_commit_hash: bool = False):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, request, *args, **kwargs):
            start_time = time.time()
            try:
                # Execute the function
                result = func(self, request, *args, **kwargs)

                # Success Logging
                req_dump = request.model_dump() if hasattr(request, "model_dump") else str(request)

                commit_hash = None
                if include_commit_hash and hasattr(self, "_get_commit_hash"):
                    commit_hash = self._get_commit_hash()

                self.audit_logger.log_access(role, tool_name, req_dump, True, commit_hash=commit_hash)
                TOOL_CALLS.labels(tool=tool_name, status="success").inc()

                return result

            except Exception as e:
                # Error Logging
                req_dump = request.model_dump() if hasattr(request, "model_dump") else str(request)
                self.audit_logger.log_access(role, tool_name, req_dump, False, error=str(e))
                TOOL_CALLS.labels(tool=tool_name, status="error").inc()

                # Determine return type to construct error response
                sig = inspect.signature(func)
                return_type = sig.return_annotation

                if return_type and hasattr(return_type, "model_construct"):
                    # Use standard constructor with keyword arguments for BaseResponse derivatives
                    try:
                        return return_type(status="error", message=str(e))
                    except Exception:
                        return BaseResponse(status="error", message=str(e))

                # Fallback
                return BaseResponse(status="error", message=str(e))
            finally:
                TOOL_LATENCY.labels(tool=tool_name).observe(time.time() - start_time)
        return wrapper
    return decorator

class MCPRole(str, enum.Enum):
    VIEWER = "viewer"
    AGENT = "agent"
    ADMIN = "admin"

class MCPServer:
    current_instance = None

    def __init__(self, 
                 memory: Memory, 
                 server_name: str = "Ledgermind", 
                 storage_path: str = "ledgermind",
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

        # Initialize shared Bridge for context/telemetry
        from ledgermind.core.api.bridge import IntegrationBridge
        self.bridge = IntegrationBridge(memory_path=storage_path, memory_instance=self.memory)
        
        # Security Configuration
        self.api_key = os.environ.get("LEDGERMIND_API_KEY")
        if self.api_key:
            logger.info("API Key authentication enabled.")
        
        self._last_write_time = 0
        self._write_cooldown = 1.0 
        self._register_tools()
        
        # Subscribe to events for webhooks
        if self.webhooks:
            # Memory class has an 'events' object (EventEmitter)
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
            
        ctx: Context = getattr(self.mcp, "context", None)
        
        # If we have request context (SSE/HTTP), check headers
        if ctx and hasattr(ctx, "request_context") and ctx.request_context:
            headers = getattr(ctx.request_context.request, "headers", {})
            provided_key = headers.get("X-API-Key") or headers.get("x-api-key")
            if provided_key != self.api_key:
                raise PermissionError("Invalid or missing X-API-Key header.")

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
        now = time.time()
        if now - self._last_write_time < self._write_cooldown:
            raise PermissionError(f"Rate limit exceeded: please wait {self._write_cooldown}s between operations.")
        self._last_write_time = now

    # --- Tool Handlers ---

    def _get_commit_hash(self) -> Optional[str]:
        return self.memory.semantic.get_head_hash()

    @measure_and_log("record_decision", include_commit_hash=True)
    def handle_record_decision(self, request: RecordDecisionRequest) -> DecisionResponse:
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
        return DecisionResponse(status="success", decision_id=dec_id)

    @measure_and_log("supersede_decision", include_commit_hash=True)
    def handle_supersede_decision(self, request: SupersedeDecisionRequest) -> DecisionResponse:
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
        return DecisionResponse(status="success", decision_id=dec_id)

    @measure_and_log("search_decisions")
    def handle_search(self, request: SearchDecisionsRequest) -> SearchResponse:
        self._validate_auth()
        self._check_capability("read")
        results = self.memory.search_decisions(
            request.query,
            limit=request.limit,
            offset=request.offset,
            namespace=request.namespace,
            mode=request.mode
        )
        return SearchResponse(status="success", results=results)

    @measure_and_log("accept_proposal", include_commit_hash=True)
    def handle_accept_proposal(self, request: AcceptProposalRequest) -> BaseResponse:
        self._check_capability("accept")
        self.memory.accept_proposal(request.proposal_id)
        return BaseResponse(status="success", message="Accepted")

    def _register_tools(self):
        """
        Регистрация инструментов. FastMCP автоматически использует аннотации типов 
        Pydantic моделей для генерации JSON-схем инструментов.
        """
        tools = LedgerMindTools(self)

        self.mcp.tool()(tools.record_decision)
        self.mcp.tool()(tools.supersede_decision)
        self.mcp.tool()(tools.search_decisions)
        self.mcp.tool()(tools.accept_proposal)
        self.mcp.tool()(tools.sync_git_history)
        self.mcp.tool()(tools.forget_memory)
        self.mcp.tool()(tools.visualize_graph)
        self.mcp.tool()(tools.get_memory_stats)
        self.mcp.tool()(tools.bootstrap_project_context)
        self.mcp.tool()(tools.get_environment_health)
        self.mcp.tool()(tools.get_audit_logs)
        self.mcp.tool()(tools.export_memory_bundle)
        self.mcp.tool()(tools.get_api_specification)
        self.mcp.tool()(tools.get_relevant_context)
        self.mcp.tool()(tools.record_interaction)
        self.mcp.tool()(tools.link_interaction_to_decision)

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
              storage_path: str = "ledgermind", 
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
