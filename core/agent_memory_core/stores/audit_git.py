import subprocess
import os
import time
import logging
from typing import List, Optional
from agent_memory_core.stores.interfaces import AuditProvider

logger = logging.getLogger("agent-memory-core.audit.git")

class GitAuditProvider(AuditProvider):
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def _run_git(self, args: List[str], max_retries: int = 15):
        last_error = ""
        for i in range(max_retries):
            try:
                return subprocess.run(["git"] + args, cwd=self.repo_path, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                last_error = e.stderr.decode()
                combined = last_error + "\n" + e.stdout.decode()
                if any(msg in combined for msg in ["nothing to commit", "working tree clean", "no changes added", "nothing added"]):
                    return e
                if any(msg in last_error for msg in ["index.lock", "File exists", "could not lock", "Another git process"]):
                    time.sleep(0.3 * (1.4 ** i))
                    continue
                raise e
        raise RuntimeError(f"Git failed after {max_retries} retries: {last_error}")

    def initialize(self):
        if not os.path.exists(os.path.join(self.repo_path, ".git")):
            logger.info(f"Initializing new Git repository at {self.repo_path}")
            self._run_git(["init"])
            
            user_name = os.environ.get("GIT_AUTHOR_NAME", "agent-memory-core")
            user_email = os.environ.get("GIT_AUTHOR_EMAIL", "agent@memory.local")
            
            self._run_git(["config", "user.name", user_name])
            self._run_git(["config", "user.email", user_email])
            
            gitignore_path = os.path.join(self.repo_path, ".gitignore")
            with open(gitignore_path, "a") as f:
                f.write("\n.lock\n.quarantine/\n.tx_backup/\n")
            self._run_git(["add", ".gitignore"])
            self._run_git(["commit", "-m", "Initial commit", "--"])

    def add_artifact(self, relative_path: str, content: str, commit_msg: str):
        self._run_git(["add", "--", relative_path])
        self._run_git(["commit", "-m", commit_msg, "--", relative_path])

    def update_artifact(self, relative_path: str, content: str, commit_msg: str):
        self._run_git(["add", "--", relative_path])
        self._run_git(["commit", "-m", commit_msg, "--", relative_path])

    def get_head_hash(self) -> Optional[str]:
        try:
            res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_path, capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception: pass
        return None

    def purge_artifact(self, relative_path: str):
        try:
            self._run_git(["rm", "--cached", relative_path])
            self._run_git(["commit", "-m", f"Purge: {relative_path}", "--"])
        except Exception as e:
            logger.warning(f"Failed to purge {relative_path} from git: {e}")

    def commit_transaction(self, message: str):
        self._run_git(["commit", "-m", message, "--"])
