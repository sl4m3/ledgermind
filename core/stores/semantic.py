import os
import subprocess
import yaml
import time
import logging
from typing import List, Optional, Any
from core.schemas import MemoryEvent, TrustBoundary
from stores.semantic_store.integrity import IntegrityChecker, IntegrityViolation
from stores.semantic_store.transitions import TransitionValidator
from stores.semantic_store.loader import MemoryLoader

# Setup structured logging
logger = logging.getLogger("agent-memory-core.semantic")

class SemanticStore:
    """
    Store for semantic memory (long-term decisions) using Git for versioning.
    """
    def __init__(self, repo_path: str, trust_boundary: TrustBoundary = TrustBoundary.AGENT_WITH_INTENT):
        """
        Initialize the semantic store.
        
        :param repo_path: Path to the Git repository.
        :param trust_boundary: Security boundary for modifications.
        """
        self.repo_path = repo_path
        self.trust_boundary = trust_boundary
        self.lock_file = os.path.join(repo_path, ".lock")
        
        self._init_repo()
        self._recover_dirty_state()
        
        # Final validation of the whole state
        IntegrityChecker.validate(self.repo_path)

    def _init_repo(self):
        """
        Initialize the Git repository and configure user identity.
        """
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path, exist_ok=True)
        
        if not os.path.exists(os.path.join(self.repo_path, ".git")):
            logger.info(f"Initializing new Git repository at {self.repo_path}")
            subprocess.run(["git", "init"], cwd=self.repo_path, capture_output=True, check=True)
            
            user_name = os.environ.get("GIT_AUTHOR_NAME", "agent-memory-core")
            user_email = os.environ.get("GIT_AUTHOR_EMAIL", "agent@memory.local")
            
            subprocess.run(["git", "config", "user.name", user_name], cwd=self.repo_path, check=True)
            subprocess.run(["git", "config", "user.email", user_email], cwd=self.repo_path, check=True)

    def _recover_dirty_state(self):
        """
        Checks for untracked or modified files (e.g. after a crash) and tries to recover.
        """
        status = subprocess.run(["git", "status", "--short"], cwd=self.repo_path, capture_output=True, text=True).stdout
        if status:
            logger.warning(f"Dirty state detected in Semantic Store:\n{status}")
            # Automatically try to stage and commit untracked .md files to maintain integrity
            untracked = [line[3:].strip() for line in status.splitlines() if line.startswith("??") and line.endswith(".md")]
            for f in untracked:
                logger.info(f"Recovering untracked file: {f}")
                try:
                    subprocess.run(["git", "add", "--", f], cwd=self.repo_path, check=True)
                    subprocess.run(["git", "commit", "-m", f"Recovery: auto-fix untracked file {f}", "--"], cwd=self.repo_path, check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to recover {f}: {e}")

    def _acquire_lock(self):
        """
        Acquire a simple file-based lock.
        """
        timeout = 5
        start_time = time.time()
        while True:
            try:
                # Use exclusive creation to avoid race condition
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w") as f:
                    f.write(str(os.getpid()))
                return
            except FileExistsError:
                if time.time() - start_time > timeout:
                    raise TimeoutError("Could not acquire lock on Semantic Store")
                time.sleep(0.1)

    def _release_lock(self):
        """
        Release the file-based lock.
        """
        if os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)
            except OSError:
                pass

    def _enforce_trust(self, event: Optional[MemoryEvent] = None):
        """
        Enforce the trust boundary policy.
        """
        if self.trust_boundary == TrustBoundary.HUMAN_ONLY:
            if not event or (event.source == "agent" and event.kind == "decision"):
                raise PermissionError("Trust Boundary Violation: Unauthorized modification attempt.")

    def save(self, event: MemoryEvent) -> str:
        """
        Save a memory event to the semantic store.
        """
        self._enforce_trust(event)
        self._acquire_lock()
        try:
            filename = f"{event.kind}_{event.timestamp.strftime('%Y%m%d_%H%M%S_%f')}.md"
            file_path = os.path.join(self.repo_path, filename)
            
            data = event.model_dump(mode='json')
            title = event.content if len(event.content) < 100 else event.kind
            body = f"# {title}\n\nRecorded from source: {event.source}\n"
            
            if event.kind == "decision":
                ctx = event.context.model_dump() if hasattr(event.context, 'model_dump') else event.context
                body += f"\n## Rationale\n{ctx.get('rationale', '')}\n"
                
            content = MemoryLoader.stringify(data, body)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            logger.info(f"Saving semantic event to {filename}", extra={"kind": event.kind, "source": event.source})
            
            subprocess.run(["git", "add", "--", filename], cwd=self.repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Add {event.kind}: {event.content[:50]}", "--"], 
                           cwd=self.repo_path, check=True, capture_output=True)
            return filename
        finally:
            self._release_lock()

    def update_decision(self, filename: str, updates: dict, commit_msg: str):
        """
        Update an existing decision in the semantic store.
        """
        self._enforce_trust()
        self._acquire_lock()
        try:
            file_path = os.path.join(self.repo_path, filename)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Decision file not found: {filename}")
                
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            old_data, body = MemoryLoader.parse(content)
            new_data = yaml.safe_load(yaml.dump(old_data))
            if "context" not in new_data:
                new_data["context"] = {}
            new_data["context"].update(updates)

            TransitionValidator.validate_update(old_data, new_data)

            new_content = MemoryLoader.stringify(new_data, body)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            logger.info(f"Updating decision {filename}: {commit_msg}")
            
            subprocess.run(["git", "add", "--", filename], cwd=self.repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", commit_msg, "--"], cwd=self.repo_path, check=True, capture_output=True)
        finally:
            self._release_lock()

        def list_decisions(self) -> List[str]:
            """
            List all semantic records.
            """
            return [f for f in os.listdir(self.repo_path) if f.endswith(".md") or f.endswith(".yaml")]
    
        def list_active_conflicts(self, target: str) -> List[str]:
            """
            Identify active decisions that conflict with the given target.
            """
            conflicts = []
            for filename in self.list_decisions():
                try:
                    with open(os.path.join(self.repo_path, filename), 'r', encoding='utf-8') as f:
                        data, _ = MemoryLoader.parse(f.read())
                        ctx = data.get("context", {})
                        if (data.get("kind") == "decision" and 
                            ctx.get("target") == target and 
                            ctx.get("status") == "active"):
                            conflicts.append(filename)
                except Exception:
                    continue
            return conflicts
    
        def find_proposal(self, target: str) -> Optional[str]:
            """
            Finds an existing draft proposal for a given target.
            """
            for filename in self.list_decisions():
                try:
                    with open(os.path.join(self.repo_path, filename), 'r', encoding='utf-8') as f:
                        data, _ = MemoryLoader.parse(f.read())
                        ctx = data.get("context", {})
                        if (data.get("kind") == "proposal" and 
                            ctx.get("target") == target and 
                            ctx.get("status") == "draft"):
                            return filename
                except Exception:
                    continue
            return None
    