import logging
from typing import Any, Dict, List, Optional
import os
import enum
import httpx
import asyncio
import time
import hmac
import threading
import functools
import inspect
import subprocess
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

def redact_payload(data: Any) -> Any:
    """Redacts potentially sensitive fields from audit logs."""
    if isinstance(data, dict):
        redacted = data.copy()
        for key in ["content", "rationale", "rationale_val"]:
            if key in redacted and isinstance(redacted[key], str):
                val = redacted[key]
                if len(val) > 40:
                    redacted[key] = f"{val[:15]}...[REDACTED]...{val[-15:]}"
        return redacted
    return data

def measure_and_log(tool_name: str, role: str = "agent", include_commit_hash: bool = False):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, request, *args, **kwargs):
            start_time = time.time()
            try:
                # Execute the function
                result = func(self, request, *args, **kwargs)

                # Success Logging
                req_data = request.model_dump() if hasattr(request, "model_dump") else str(request)
                req_dump = redact_payload(req_data)

                commit_hash = None
                if include_commit_hash and hasattr(self, "_get_commit_hash"):
                    commit_hash = self._get_commit_hash()

                self.audit_logger.log_access(role, tool_name, req_dump, True, commit_hash=commit_hash)
                TOOL_CALLS.labels(tool_name, "success").inc()

                return result

            except Exception as e:
                # Error Logging
                req_data = request.model_dump() if hasattr(request, "model_dump") else str(request)
                req_dump = redact_payload(req_data)
                self.audit_logger.log_access(role, tool_name, req_dump, False, error=str(e))
                TOOL_CALLS.labels(tool_name, "error").inc()

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
                TOOL_LATENCY.labels(tool_name).observe(time.time() - start_time)
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
                 webhooks: Optional[List[str]] = None,
                 client: Optional[str] = None):

        self.memory = memory
        self.default_role = default_role
        self.capabilities = capabilities if capabilities is not None else {
            "read": True, "propose": True, "supersede": True,
            "accept": True, "sync": True, "purge": False,
            "maintenance": True
        }
        self.metrics_port = metrics_port
        self.rest_port = rest_port
        self.webhooks = webhooks or []
        self._webhook_semaphore = asyncio.Semaphore(5) # Limit concurrent webhooks
        self._active_tasks: List[asyncio.Task] = []
        self._rest_stop_event: Optional[asyncio.Event] = None
        self.client = client  # Track which client started this MCP server

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

        # Update client config if provided
        if client:
            self.memory.semantic.meta.set_config("client", client)
            logger.info(f"Client configured: {client}")

        self._last_write_time = 0
        self._write_cooldown = 1.0
        self._register_tools()
        self._register_session()

        # Subscribe to events for webhooks
        if self.webhooks:
            # Memory class has an 'events' object (EventEmitter)
            if hasattr(self.memory, 'events'):
                self.memory.events.subscribe(self._trigger_webhooks)

        # Initialize Background Worker (Active Loop)
        self.storage_path = os.path.abspath(storage_path)
        self._worker_process: Optional[subprocess.Popen] = None

        # Start orphan monitor thread
        self._stop_event = threading.Event()
        self._orphan_thread = threading.Thread(target=self._orphan_monitor, name="OrphanMonitor", daemon=True)
        self._orphan_thread.start()

        if start_worker:
            self._start_background_worker()

    def _orphan_monitor(self):
        """Periodically checks if the parent process is still alive and reaps child processes."""
        while not self._stop_event.is_set():
            # 1. Child Reaping (Zombie prevention)
            if self._worker_process is not None:
                # poll() non-blockingly checks if the process has terminated
                exit_code = self._worker_process.poll()
                if exit_code is not None:
                    logger.warning(f"Background worker (PID {self._worker_process.pid}) terminated with code {exit_code}.")
                    # The zombie is now reaped by the poll() call in subprocess
                    self._worker_process = None

            # 2. Parent detection (Unix/Android only)
            # In Unix/Android, if parent dies, process is re-parented to PID 1
            if os.getppid() == 1:
                logger.warning("Parent process died (orphaned). Initiating self-shutdown.")
                self.stop()
                os._exit(0) 
            time.sleep(5.0) # Check every 5 seconds

    def _register_session(self):
        """Registers the current PID as an active session for the background worker."""
        # V7.8: sessions folder is inside storage path
        storage = os.path.abspath(self.memory.storage_path)
        sessions_dir = os.path.join(storage, "sessions")
        try:
            os.makedirs(sessions_dir, exist_ok=True)
            session_file = os.path.join(sessions_dir, f"{os.getpid()}.lock")
            with open(session_file, 'w') as f:
                f.write(str(os.getpid()))
            logger.info(f"Session registered: {session_file}")

            # Ensure file is removed on exit
            import atexit
            def _cleanup():
                try:
                    if os.path.exists(session_file):
                        os.remove(session_file)
                        logger.debug(f"Session cleaned up: {session_file}")
                except: pass
            atexit.register(_cleanup)
        except Exception as e:
            logger.error(f"Failed to register session in {sessions_dir}: {e}")

    def _start_background_worker(self):
        """Starts the background worker as a fully detached daemon-like process."""
        import subprocess
        import sys
        import os

        log_abs = os.path.abspath(os.path.join(os.getcwd(), "logs/background_worker.log"))
        err_log_abs = os.path.abspath(os.path.join(os.getcwd(), "logs/worker_error.log"))

        # Ensure log directory exists
        os.makedirs(os.path.dirname(log_abs), exist_ok=True)

        # Get absolute path to background.py script to run it directly
        import ledgermind.server.background as bg_module
        script_path = os.path.abspath(bg_module.__file__)

        cmd = [
            sys.executable, script_path,
            "--storage", self.storage_path,
            "--log", log_abs
        ]
        
        # Pass client to background worker if set
        if self.client:
            cmd.extend(["--client", self.client])

        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
            env = {**os.environ, "PYTHONPATH": base_dir}
            
            # Pass client via environment variable as well
            if self.client:
                env["LEDGERMIND_CLIENT"] = self.client

            # We use a persistent file handle that stays open for the child process.
            # buffering=1 ensures lines are flushed quickly.
            # Using 'w' mode to start fresh on every server restart.
            err_file = open(err_log_abs, 'w', buffering=1)

            self._worker_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=err_file,
                stdin=subprocess.DEVNULL,
                env=env,
                close_fds=True
            )
            logger.info(f"Background Worker started (PID: {self._worker_process.pid}, Client: {self.client or 'unknown'})")
        except Exception as e:
            logger.error(f"Failed to start background worker: {e}")

    def _trigger_webhooks(self, event_type: str, data: Any):
        """Dispatches event to all registered webhook URLs with concurrency limits."""
        if not self.webhooks: return
        
        async def _notify():
            async with self._webhook_semaphore:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    payload = {"event": event_type, "data": data, "timestamp": time.time()}
                    tasks = [client.post(url, json=payload) for url in self.webhooks]
                    await asyncio.gather(*tasks, return_exceptions=True)
        
        # Run in background and track the task
        task = asyncio.create_task(_notify())
        self._active_tasks.append(task)
        # Periodic cleanup of completed tasks
        self._active_tasks = [t for t in self._active_tasks if not t.done()]

    def _validate_auth(self):
        """Validates the request against the configured API key."""
        if not self.api_key:
            return
            
        ctx: Context = getattr(self.mcp, "context", None)
        
        # If we have request context (SSE/HTTP), check headers
        if ctx and hasattr(ctx, "request_context") and ctx.request_context:
            headers = getattr(ctx.request_context.request, "headers", {})
            provided_key = headers.get("X-API-Key") or headers.get("x-api-key")
            if self.api_key is not None:
                if provided_key is None or not hmac.compare_digest(provided_key, self.api_key):
                    raise PermissionError("Invalid or missing X-API-Key header.")

    def _validate_isolation(self, decision_ids: List[str]):
        """
        Enforces that agents can only supersede decisions created by other agents.
        Human-created decisions are protected and require ADMIN role to supersede.
        """
        if self.default_role == MCPRole.ADMIN:
            return

        for d_id in decision_ids:
            # Fetch metadata from the database
            meta = self.memory.semantic.meta.get_by_fid(d_id)
            if meta:
                # Check source in context (stored as JSON in meta)
                try:
                    import json
                    ctx = json.loads(meta.get('context_json', '{}'))
                    source = ctx.get('source', 'human') # Default to human for safety
                    
                    if source != 'agent' and '[via MCP]' not in (meta.get('content', '') + meta.get('title', '')):
                        raise PermissionError(
                            f"Security Violation: Decision {d_id} was created by a human ('{source}') "
                            "and cannot be modified by an agent. Requires ADMIN role."
                        )
                except (json.JSONDecodeError, TypeError):
                    # If metadata is corrupt, assume human for safety
                    raise PermissionError(f"Security Violation: Metadata for {d_id} is unreadable. Access denied.")

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
        self._validate_auth()
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
        self.mcp.tool()(tools.repair_language)

    def stop(self):
        """Gracefully shuts down the server. The worker will stay alive if other sessions exist."""
        logger.info("Shutting down MCPServer...")

        # 1. Signal REST Gateway to stop
        if self._rest_stop_event:
            logger.info("Signaling REST Gateway shutdown...")
            self._rest_stop_event.set()

        # 2. Cleanup session file (Worker will detect this and shutdown if no other sessions)
        # V7.8: sessions folder is inside storage path
        storage = os.path.abspath(self.memory.storage_path)
        sessions_dir = os.path.join(storage, "sessions")
        session_file = os.path.join(sessions_dir, f"{os.getpid()}.lock")
        try:
            if os.path.exists(session_file):
                os.remove(session_file)
                logger.info(f"Session unregistered: {session_file}")
        except Exception as e:
            logger.debug(f"Failed to cleanup session file: {e}")

        # 3. We NO LONGER kill the worker process here. 
        # The worker manages its own lifecycle based on active sessions.
        self._worker_process = None

        # 4. Wait for background webhooks to finish
        if self._active_tasks:
            logger.info(f"Waiting for {len(self._active_tasks)} background webhook tasks...")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(asyncio.gather(*self._active_tasks, return_exceptions=True))
            except:
                pass

        if hasattr(self, 'memory') and hasattr(self.memory, 'vector'):
            self.memory.vector.close()

        logger.info("MCPServer shutdown complete.")

    def run(self):
        if self.metrics_port:
            logger.info(f"Starting Prometheus metrics server on port {self.metrics_port}")
            start_http_server(self.metrics_port)
        
        if self.rest_port:
            logger.info(f"Starting REST Gateway on port {self.rest_port}")
            from ledgermind.server.gateway import run_gateway
            self._rest_stop_event = asyncio.Event()
            
            def start_rest():
                asyncio.run(run_gateway(self.memory, port=self.rest_port, stop_event=self._rest_stop_event))

            gateway_thread = threading.Thread(
                target=start_rest,
                daemon=True
            )
            gateway_thread.start()
            
        # Orphan detection is disabled to support independent worker lifecycle and Termux environment
        
        try:
            self.mcp.run()
        finally:
            self.stop()

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
