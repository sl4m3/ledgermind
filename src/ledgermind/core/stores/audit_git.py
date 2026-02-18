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
        for i in range(max_retries):
            try:
                return subprocess.run(["git"] + args, cwd=self.repo_path, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                last_error = e.stderr.decode()
                combined = last_error + "\n" + e.stdout.decode()
                if any(msg in combined for msg in ["nothing to commit", "working tree clean", "no changes added", "nothing added"]):
                    return e
                if any(msg in last_error for msg in ["index.lock", "File exists", "could not lock", "cannot lock", "Another git process"]):
                    time.sleep(0.3 * (1.4 ** i))
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
        self.run(["commit", "--allow-empty", "-m", message])
