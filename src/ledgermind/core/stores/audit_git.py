import subprocess
import os
import time
import logging
from typing import List, Optional
from ledgermind.core.stores.interfaces import AuditProvider

logger = logging.getLogger("ledgermind-core.audit.git")

class GitAuditProvider(AuditProvider):
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self._initialized = False

    def run(self, args: List[str], max_retries: int = 15):
        last_error = ""
        # Ensure we always use --no-pager to avoid hanging in interactive environments
        cmd = ["git", "--no-pager"] + args
        for i in range(max_retries):
            try:
                return subprocess.run(cmd, cwd=self.repo_path, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                last_error = e.stderr.decode()
                combined = last_error + "\n" + e.stdout.decode()
                
                # Check for "nothing to commit" which is not a fatal error for us
                if any(msg in combined for msg in ["nothing to commit", "working tree clean", "no changes added", "nothing added"]):
                    return e
                
                # Handle lock contention with exponential backoff
                if any(msg in last_error for msg in ["index.lock", "File exists", "could not lock", "cannot lock", "Another git process"]):
                    wait_time = 0.3 * (1.4 ** i)
                    logger.warning(f"Git lock contention detected. Retrying in {wait_time:.2f}s... (Attempt {i+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                raise e
        raise RuntimeError(f"Git failed after {max_retries} retries: {last_error}")

    def initialize(self):
        if self._initialized:
            return
            
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path, exist_ok=True)
            
        if not os.path.exists(os.path.join(self.repo_path, ".git")):
            logger.info(f"Initializing new Git repository at {self.repo_path}")
            try:
                self.run(["init", "--quiet"])
                
                user_name = os.environ.get("GIT_AUTHOR_NAME", "ledgermind-core")
                user_email = os.environ.get("GIT_AUTHOR_EMAIL", "agent@memory.local")
                
                self.run(["config", "user.name", user_name])
                self.run(["config", "user.email", user_email])
                
                gitignore_path = os.path.join(self.repo_path, ".gitignore")
                if not os.path.exists(gitignore_path):
                    with open(gitignore_path, "w", encoding="utf-8") as f:
                        f.write("\n.lock\n.quarantine/\n.tx_backup/\n")
                
                self.run(["add", ".gitignore"])
                self.run(["commit", "--quiet", "--allow-empty", "-m", "Initial commit"])
            except Exception as e:
                if not os.path.exists(os.path.join(self.repo_path, ".git")):
                    raise e
        
        self._initialized = True

    def is_healthy(self) -> bool:
        """Checks if the git repository is in a valid state."""
        try:
            self.run(["rev-parse", "--is-inside-work-tree"])
            return True
        except Exception:
            return False

    def add_artifact(self, relative_path: str, content: str, commit_msg: str):
        self.run(["add", "--", relative_path])
        self.run(["commit", "-m", commit_msg, "--", relative_path])

    def update_artifact(self, relative_path: str, content: str, commit_msg: str):
        self.run(["add", "--", relative_path])
        self.run(["commit", "-m", commit_msg, "--", relative_path])

    def get_head_hash(self) -> Optional[str]:
        try:
            res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_path, capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception: pass
        return None

    def purge_artifact(self, relative_path: str):
        try:
            self.run(["rm", "--cached", "--", relative_path])
            self.run(["commit", "-m", f"Purge: {relative_path}"])
        except Exception as e:
            logger.warning(f"Failed to purge {relative_path} from git: {e}")

    def commit_transaction(self, message: str):
        self.run(["add", "."])
        # Only commit if there are staged changes
        res = self.run(["status", "--porcelain"])
        if res.stdout.strip():
            self.run(["commit", "-m", message])
        else:
            logger.debug("No changes to commit in transaction.")

    def get_history(self, relative_path: str) -> List[dict]:
        """Retrieves commit history for a specific file."""
        try:
            # Format: hash|author|date|message
            res = self.run(["log", "--format=%H|%an|%ai|%s", "--", relative_path])
            lines = res.stdout.decode().strip().split('\n')
            history = []
            for line in lines:
                if not line: continue
                parts = line.split('|')
                if len(parts) >= 4:
                    history.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "timestamp": parts[2],
                        "message": parts[3]
                    })
            return history
        except Exception:
            return []
