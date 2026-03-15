import os
import logging
import shutil
import subprocess
import collections
from typing import Dict, Any
from ..base_service import MemoryService
from ledgermind.core.core.schemas import TrustBoundary

logger = logging.getLogger("ledgermind.core.api.services.health")

class HealthService(MemoryService):
    """
    Service responsible for system diagnostics, health checks, and statistics.
    """
    
    def check_health(self) -> Dict[str, Any]:
        """Performs a pre-flight check of the environment."""
        results = {
            "git_available": False,
            "git_configured": False,
            "storage_writable": False,
            "disk_space_ok": False,
            "repo_healthy": False,
            "vector_available": False,
            "storage_locked": False,
            "lock_owner": None,
            "errors": [],
            "warnings": []
        }
        
        # 0. Check Lock Status
        try:
            if not self.semantic._fs_lock.acquire(exclusive=False, timeout=0):
                results["storage_locked"] = True
                try:
                    with open(self.semantic.lock_file, 'r') as f:
                        results["lock_owner"] = f.read().strip()
                except Exception: pass
                results["warnings"].append(f"Storage is currently locked by PID: {results['lock_owner'] or 'unknown'}")
            else:
                self.semantic._fs_lock.release()
        except Exception as e:
            logger.debug(f"Lock check failed: {e}")

        # 0.1 Check Vector Search
        from ledgermind.core.stores.vector import _is_transformers_available, _is_llama_available, EMBEDDING_AVAILABLE, LLAMA_AVAILABLE
        vector_model = self.context.config.vector_model
        if vector_model.endswith(".gguf"):
            avail = LLAMA_AVAILABLE if LLAMA_AVAILABLE is not None else _is_llama_available()
            results["vector_available"] = avail
            if not avail: results["warnings"].append("llama-cpp-python not installed. GGUF disabled.")
            elif not os.path.exists(vector_model): results["warnings"].append(f"GGUF model missing: {vector_model}")
        else:
            avail = EMBEDDING_AVAILABLE if EMBEDDING_AVAILABLE is not None else _is_transformers_available()
            results["vector_available"] = avail
            if not avail: results["warnings"].append("Sentence-transformers not installed. Vector search disabled.")

        # 1. Check Git
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
            results["git_available"] = True
            try:
                name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
                email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
                if name and email: results["git_configured"] = True
                else: results["warnings"].append("Git user.name or user.email not configured.")
            except Exception: pass
        except Exception:
            results["errors"].append("Git is not installed or not in PATH.")
        
        # 2. Check Storage
        path = self.context.storage_path
        if os.path.exists(path):
            if os.access(path, os.W_OK):
                results["storage_writable"] = True
                try:
                    usage = shutil.disk_usage(path)
                    if usage.free / (1024 * 1024) > 50: results["disk_space_ok"] = True
                    else: results["warnings"].append("Low disk space.")
                except Exception: results["disk_space_ok"] = True
            else: results["errors"].append(f"Storage path is not writable: {path}")
        else:
            try:
                os.makedirs(path, exist_ok=True)
                results["storage_writable"] = True
                results["disk_space_ok"] = True
            except Exception as e: results["errors"].append(f"Failed to create storage path: {e}")
                
        # 3. Check Repo Health
        from ledgermind.core.stores.audit_git import GitAuditProvider
        if isinstance(self.semantic.audit, GitAuditProvider):
            try:
                self.semantic.audit.initialize()
                results["repo_healthy"] = True
            except Exception as e: results["errors"].append(f"Git repo failed: {e}")
                
        if results["errors"] and self.context.trust_boundary == TrustBoundary.AGENT_WITH_INTENT:
             logger.error(f"Environment check failed: {', '.join(results['errors'])}")
        
        results["healthy"] = len(results["errors"]) == 0
        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Returns diagnostic statistics."""
        all_meta = self.semantic.meta.list_all()
        phases = dict(collections.Counter(m.get('phase', 'pattern') for m in all_meta))
        vitality = dict(collections.Counter(m.get('vitality', 'active') for m in all_meta))

        return {
            "semantic_total": len(all_meta),
            "phases": phases,
            "vitality": vitality,
            "namespace": self.context.namespace,
            "storage_path": self.context.storage_path
        }
