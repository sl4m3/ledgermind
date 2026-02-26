import json
import os
import time
from typing import List, Optional, TYPE_CHECKING
from ledgermind.server.contracts import (
    RecordDecisionRequest, SupersedeDecisionRequest,
    SearchDecisionsRequest, AcceptProposalRequest,
    SyncGitResponse
)
from ledgermind.server.metrics import TOOL_CALLS, TOOL_LATENCY

if TYPE_CHECKING:
    from ledgermind.server.server import MCPServer

class LedgerMindTools:
    def __init__(self, server: "MCPServer"):
        self.server = server

    def record_decision(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None, namespace: str = "default") -> str:
        """Records a strategic decision into semantic memory."""
        req = RecordDecisionRequest(title=title, target=target, rationale=rationale, consequences=consequences or [], namespace=namespace)
        return self.server.handle_record_decision(req).model_dump_json()

    def supersede_decision(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None, namespace: str = "default") -> str:
        """Replaces old decisions with a new one."""
        req = SupersedeDecisionRequest(title=title, target=target, rationale=rationale, old_decision_ids=old_decision_ids, consequences=consequences or [], namespace=namespace)
        return self.server.handle_supersede_decision(req).model_dump_json()

    def search_decisions(self, query: str, limit: int = 5, offset: int = 0, namespace: str = "default", mode: str = "balanced") -> str:
        """Keyword search for active decisions and rules. Mode can be 'strict', 'balanced', or 'audit'."""
        req = SearchDecisionsRequest(query=query, limit=limit, offset=offset, namespace=namespace, mode=mode)
        return self.server.handle_search(req).model_dump_json()

    def accept_proposal(self, proposal_id: str) -> str:
        """Converts a draft proposal into an active decision."""
        req = AcceptProposalRequest(proposal_id=proposal_id)
        return self.server.handle_accept_proposal(req).model_dump_json()

    def sync_git_history(self, repo_path: str = ".", limit: int = 20) -> str:
        """Syncs Git commit history into episodic memory."""
        start_time = time.time()
        try:
            self.server._check_capability("sync")
            count = self.server.memory.sync_git(repo_path=repo_path, limit=limit)
            self.server.audit_logger.log_access("agent", "sync_git_history", {"repo_path": repo_path, "limit": limit}, True)
            TOOL_CALLS.labels(tool="sync_git_history", status="success").inc()
            return SyncGitResponse(status="success", indexed_commits=count).model_dump_json()
        except Exception as e:
            self.server.audit_logger.log_access("agent", "sync_git_history", {"repo_path": repo_path, "limit": limit}, False, error=str(e))
            TOOL_CALLS.labels(tool="sync_git_history", status="error").inc()
            return json.dumps({"status": "error", "message": str(e)})
        finally:
            TOOL_LATENCY.labels(tool="sync_git_history").observe(time.time() - start_time)

    def forget_memory(self, decision_id: str) -> str:
        """Hard-deletes a memory from filesystem and metadata (GDPR purge)."""
        start_time = time.time()
        try:
            self.server._check_capability("purge")
            self.server.memory.forget(decision_id)
            self.server.audit_logger.log_access("admin", "forget_memory", {"id": decision_id}, True)
            TOOL_CALLS.labels(tool="forget_memory", status="success").inc()
            return json.dumps({"status": "success", "message": f"Forgotten {decision_id}"})
        except Exception as e:
            self.server.audit_logger.log_access("admin", "forget_memory", {"id": decision_id}, False, error=str(e))
            TOOL_CALLS.labels(tool="forget_memory", status="error").inc()
            return json.dumps({"status": "error", "message": str(e)})
        finally:
            TOOL_LATENCY.labels(tool="forget_memory").observe(time.time() - start_time)

    def visualize_graph(self, target: Optional[str] = None) -> str:
        """Generates a Mermaid diagram of the knowledge evolution graph. Optional 'target' to filter."""
        start_time = time.time()
        try:
            self.server._check_capability("read")
            mermaid_code = self.server.memory.generate_knowledge_graph(target=target)
            self.server.audit_logger.log_access("agent", "visualize_graph", {"target": target}, True)
            TOOL_CALLS.labels(tool="visualize_graph", status="success").inc()
            return json.dumps({"status": "success", "mermaid": mermaid_code})
        except Exception as e:
            self.server.audit_logger.log_access("agent", "visualize_graph", {"target": target}, False, error=str(e))
            TOOL_CALLS.labels(tool="visualize_graph", status="error").inc()
            return json.dumps({"status": "error", "message": str(e)})
        finally:
            TOOL_LATENCY.labels(tool="visualize_graph").observe(time.time() - start_time)

    def get_memory_stats(self) -> str:
        """Returns memory usage statistics."""
        start_time = time.time()
        try:
            self.server._check_capability("read")
            stats = self.server.memory.get_stats()
            self.server.audit_logger.log_access("agent", "get_memory_stats", {}, True)
            TOOL_CALLS.labels(tool="get_memory_stats", status="success").inc()
            return json.dumps({"status": "success", "stats": stats})
        except Exception as e:
            self.server.audit_logger.log_access("agent", "get_memory_stats", {}, False, error=str(e))
            TOOL_CALLS.labels(tool="get_memory_stats", status="error").inc()
            return json.dumps({"status": "error", "message": str(e)})
        finally:
            TOOL_LATENCY.labels(tool="get_memory_stats").observe(time.time() - start_time)

    def bootstrap_project_context(self, path: str = ".") -> str:
        """
        Analyzes the project structure and key files.
        The agent MUST use the returned information to call `record_decision`
        separately for different semantic areas (e.g. one for 'Architecture',
        one for 'Dependencies', one for 'File Structure'). Do not cram everything into one decision.
        """
        start_time = time.time()
        try:
            self.server._check_capability("read")
            self.server._check_capability("propose")
            from ledgermind.server.tools.scanner import ProjectScanner
            scanner = ProjectScanner(path)
            result = scanner.scan()
            self.server.audit_logger.log_access("agent", "bootstrap_project_context", {"path": path}, True)
            TOOL_CALLS.labels(tool="bootstrap_project_context", status="success").inc()
            return result
        except Exception as e:
            self.server.audit_logger.log_access("agent", "bootstrap_project_context", {"path": path}, False, error=str(e))
            TOOL_CALLS.labels(tool="bootstrap_project_context", status="error").inc()
            return json.dumps({"status": "error", "message": str(e)})
        finally:
            TOOL_LATENCY.labels(tool="bootstrap_project_context").observe(time.time() - start_time)

    def get_environment_health(self) -> str:
        """Returns diagnostic information about the system environment (disk, git, python)."""
        start_time = time.time()
        try:
            self.server._check_capability("read")
            health = self.server.env_context.get_context()
            TOOL_CALLS.labels(tool="get_environment_health", status="success").inc()
            return json.dumps({"status": "success", "health": health})
        except Exception as e:
            TOOL_CALLS.labels(tool="get_environment_health", status="error").inc()
            return json.dumps({"status": "error", "message": str(e)})
        finally:
            TOOL_LATENCY.labels(tool="get_environment_health").observe(time.time() - start_time)

    def get_audit_logs(self, limit: int = 20) -> str:
        """Returns the last N lines of the MCP audit log."""
        start_time = time.time()
        try:
            self.server._check_capability("read")
            logs = self.server.audit_logger.get_logs(limit=limit)
            return json.dumps({"status": "success", "logs": logs})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
        finally:
            TOOL_LATENCY.labels(tool="get_audit_logs").observe(time.time() - start_time)

    def export_memory_bundle(self, output_filename: str = "memory_export.tar.gz") -> str:
        """Creates a full backup of the memory storage in a .tar.gz file."""
        start_time = time.time()
        try:
            self.server._check_capability("purge") # Exporting full data is a sensitive operation
            from ledgermind.core.api.transfer import MemoryTransferManager
            transfer = MemoryTransferManager(self.server.memory.storage_path)
            # Save to a temporary file in the same directory or specified path
            path = transfer.export_to_tar(output_filename)
            return json.dumps({"status": "success", "export_path": os.path.abspath(path)})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
        finally:
            TOOL_LATENCY.labels(tool="export_memory_bundle").observe(time.time() - start_time)

    def get_api_specification(self) -> str:
        """Returns the formal JSON specification (OpenRPC-like) of the Ledgermind API."""
        from ledgermind.server.specification import MCPApiSpecification
        spec = MCPApiSpecification.generate_full_spec()
        return json.dumps(spec, indent=2)

    def get_relevant_context(self, prompt: str, limit: int = 3) -> str:
        """Retrieves and formats relevant context for a given user prompt (Bridge Tool)."""
        return self.server.bridge.get_context_for_prompt(prompt, limit=limit)

    def record_interaction(self, prompt: str, response: str, success: bool = True) -> str:
        """Records a completed interaction (prompt and response) into episodic memory (Bridge Tool)."""
        self.server.bridge.record_interaction(prompt, response, success=success)
        return json.dumps({"status": "success"})

    def link_interaction_to_decision(self, event_id: int, decision_id: str) -> str:
        """Links a specific episodic event (e.g., from search) to a semantic decision as evidence."""
        start_time = time.time()
        try:
            self.server._check_capability("supersede")
            self.server.memory.link_evidence(event_id, decision_id)
            return json.dumps({"status": "success", "message": f"Linked event {event_id} to {decision_id}"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
        finally:
            TOOL_LATENCY.labels(tool="link_interaction_to_decision").observe(time.time() - start_time)
