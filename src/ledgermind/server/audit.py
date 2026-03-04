import logging
import os
from datetime import datetime
from typing import List
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

    def get_logs(self, limit: int = 50) -> List[str]:
        """Reads the last N lines from the audit log efficiently."""
        if not os.path.exists(self.log_path):
            return []
        try:
            with open(self.log_path, 'rb') as f:
                # Seek to end of file
                f.seek(0, os.SEEK_END)
                buffer = bytearray()
                pointer = f.tell()
                lines_found = 0
                
                # Read backwards in chunks
                while pointer > 0 and lines_found < limit + 1:
                    chunk_size = min(pointer, 4096)
                    pointer -= chunk_size
                    f.seek(pointer)
                    chunk = f.read(chunk_size)
                    buffer[:0] = chunk
                    lines_found = buffer.count(b'\n')
                
                # Convert back to list of strings and take the last N
                result = buffer.decode('utf-8', errors='replace').splitlines()
                return result[-limit:]
        except Exception as e:
            return [f"Error reading logs: {e}"]
