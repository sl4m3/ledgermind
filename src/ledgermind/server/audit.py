import logging
import os
from datetime import datetime
from ledgermind.server.contracts import BaseResponse

class AuditLogger:
    def __init__(self, storage_path: str):
        self.log_path = os.path.join(storage_path, "audit.log")
        self.storage_path = storage_path
        self._setup_logger()

    def _setup_logger(self):
        self.logger = logging.getLogger("agent_memory_audit")
        self.logger.setLevel(logging.INFO)
        # Ensure we don't add multiple handlers
        if not self.logger.handlers:
            if not os.path.exists(self.storage_path):
                os.makedirs(self.storage_path, exist_ok=True)
            fh = logging.FileHandler(self.log_path)
            formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

    def log_access(self, role: str, tool: str, params: dict, success: bool, error: str = None, commit_hash: str = None):
        status = "ALLOWED" if success else "DENIED"
        pid = os.getpid()
        # Mask sensitive params or large payloads
        sanitized_params = {k: v for k, v in params.items() if k not in ["old_decision_ids", "embedding"]} 
        
        msg = f"PID: {pid} | Role: {role} | Tool: {tool} | Status: {status} | Params: {sanitized_params}"
        if commit_hash:
            msg += f" | Commit: {commit_hash}"
        if error:
            msg += f" | Error: {error}"
            
        self.logger.info(msg)
