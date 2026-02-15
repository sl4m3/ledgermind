import os
import subprocess
import yaml
import time
import logging
from typing import List, Optional, Any
from agent_memory_core.core.schemas import MemoryEvent, TrustBoundary
from agent_memory_core.stores.semantic_store.integrity import IntegrityChecker, IntegrityViolation
from agent_memory_core.stores.semantic_store.transitions import TransitionValidator
from agent_memory_core.stores.semantic_store.loader import MemoryLoader

# Setup structured logging
logger = logging.getLogger("agent-memory-core.semantic")

class SemanticStore:
    """
    Store for semantic memory (long-term decisions) using Git for versioning.
    """
    def __init__(self, repo_path: str, trust_boundary: TrustBoundary = TrustBoundary.AGENT_WITH_INTENT):
        """
        Initialize the semantic store.
        """
        self.repo_path = repo_path
        self.trust_boundary = trust_boundary
        self.lock_file = os.path.join(repo_path, ".lock")
        self._lock_handle = None
        
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
            self._run_git(["init"], cwd=self.repo_path)
            
            user_name = os.environ.get("GIT_AUTHOR_NAME", "agent-memory-core")
            user_email = os.environ.get("GIT_AUTHOR_EMAIL", "agent@memory.local")
            
            self._run_git(["config", "user.name", user_name], cwd=self.repo_path)
            self._run_git(["config", "user.email", user_email], cwd=self.repo_path)
            
            # Ensure .lock is ignored by git
            gitignore_path = os.path.join(self.repo_path, ".gitignore")
            with open(gitignore_path, "a") as f:
                f.write("\n.lock\n.quarantine/\n")
            self._run_git(["add", ".gitignore"], cwd=self.repo_path)
            self._run_git(["commit", "-m", "Initial commit: ignore locks", "--"], cwd=self.repo_path)

    def _recover_dirty_state(self):
        """
        Checks for untracked or modified files and tries to recover or quarantine them.
        """
        # We need the lock to recover safely, but __init__ calls this.
        # Avoid recursion or double-locking if acquire_lock is called twice.
        self._acquire_lock()
        try:
            try:
                status_res = self._run_git(["status", "--short"], cwd=self.repo_path)
                if isinstance(status_res, Exception): return
                status = status_res.stdout.decode()
            except Exception: return

            if status:
                logger.warning(f"Dirty state detected in Semantic Store:\n{status}")
                untracked = [line[3:].strip() for line in status.splitlines() if line.startswith("??")]
                
                quarantine_path = os.path.join(self.repo_path, ".quarantine")
                
                for f in untracked:
                    # Skip internal/hidden files
                    if f.startswith(".") or f == ".lock":
                        continue
                        
                    full_f = os.path.join(self.repo_path, f)
                    # Validation check
                    is_valid = False
                    if f.endswith(".md"):
                        try:
                            with open(full_f, 'r', encoding='utf-8') as file:
                                MemoryLoader.parse(file.read())
                            is_valid = True
                        except Exception:
                            is_valid = False
                    
                    if is_valid:
                        logger.info(f"Auto-recovering valid file: {f}")
                        try:
                            self._run_git(["add", "--", f], cwd=self.repo_path)
                            self._run_git(["commit", "-m", f"Recovery: auto-fix valid untracked file {f}", "--"], cwd=self.repo_path)
                        except Exception: pass
                    else:
                        logger.error(f"Quarantining invalid/corrupted file: {f}")
                        os.makedirs(quarantine_path, exist_ok=True)
                        os.rename(full_f, os.path.join(quarantine_path, os.path.basename(f)))
        finally:
            self._release_lock()

    def _acquire_lock(self):
        """
        Acquire a robust file-based lock.
        """
        if self._lock_handle:
            return # Already locked by this instance
            
        timeout = 15 # Increase timeout for heavy parallel tests
        start_time = time.time()
        
        if not os.path.exists(self.lock_file):
            # Atomic creation of lock file if it doesn't exist
            try:
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL)
                os.close(fd)
            except FileExistsError: pass

        while True:
            try:
                # Keep file handle open to maintain lock
                self._lock_handle = open(self.lock_file, 'w')
                try:
                    import fcntl
                    fcntl.flock(self._lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (ImportError, AttributeError, OSError): 
                    # Fallback for environments without fcntl or with issues
                    pass 
                
                self._lock_handle.write(str(os.getpid()))
                self._lock_handle.flush()
                return
            except (OSError, IOError) as e:
                if self._lock_handle: self._lock_handle.close()
                self._lock_handle = None
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Could not acquire lock on Semantic Store after {timeout}s: {e}")
                time.sleep(0.1)

    def _release_lock(self):
        """
        Release the robust lock.
        """
        if self._lock_handle:
            try:
                try:
                    import fcntl
                    fcntl.flock(self._lock_handle, fcntl.LOCK_UN)
                except (ImportError, AttributeError, OSError):
                    pass
                self._lock_handle.close()
            except Exception:
                pass
            self._lock_handle = None

    def _enforce_trust(self, event: Optional[MemoryEvent] = None):
        """
        Enforce the trust boundary policy.
        """
        if self.trust_boundary == TrustBoundary.HUMAN_ONLY:
            if not event or (event.source == "agent" and event.kind == "decision"):
                raise PermissionError("Trust Boundary Violation: Unauthorized modification attempt.")

    def _run_git(self, args: List[str], cwd: str, max_retries: int = 15):
        """
        Run a git command with retries to handle index.lock conflicts.
        """
        import time
        last_error = ""
        for i in range(max_retries):
            try:
                return subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                last_error = e.stderr.decode()
                last_out = e.stdout.decode()
                combined = last_error + "\n" + last_out
                
                # Status 1 can mean "nothing to commit" (often on stdout) or "locked" (on stderr)
                if any(msg in combined for msg in [
                    "nothing to commit", 
                    "working tree clean", 
                    "no changes added to commit",
                    "nothing added to commit but untracked files present"
                ]):
                    return e # Treat as success-ish
                
                if any(msg in last_error for msg in ["index.lock", "File exists", "could not lock", "Another git process"]):
                    logger.debug(f"Git lock conflict (retry {i+1}/{max_retries}): {args}")
                    time.sleep(0.3 * (1.4 ** i)) # Progressive backoff
                    continue
                
                logger.error(f"Git Command Failed: git {' '.join(args)}\nStdout: {last_out}\nStderr: {last_error}")
                raise e
        raise RuntimeError(f"Git operation failed after {max_retries} retries: {last_error}")

    def save(self, event: MemoryEvent, namespace: Optional[str] = None) -> str:
        """
        Save a memory event to the semantic store with transactional integrity.
        """
        self._enforce_trust(event)
        self._acquire_lock()
        
        base_dir = self.repo_path
        if namespace:
            base_dir = os.path.join(self.repo_path, namespace)
            os.makedirs(base_dir, exist_ok=True)
            
        import uuid
        suffix = uuid.uuid4().hex[:8]
        filename = f"{event.kind}_{event.timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{suffix}.md"
        relative_path = os.path.join(namespace, filename) if namespace else filename
        full_path = os.path.join(self.repo_path, relative_path)
        
        try:
            data = event.model_dump(mode='json')
            title = event.content if len(event.content) < 100 else event.kind
            body = f"# {title}\n\nRecorded from source: {event.source}\n"
            
            if event.kind == "decision":
                ctx = event.context.model_dump() if hasattr(event.context, 'model_dump') else event.context
                body += f"\n## Rationale\n{ctx.get('rationale', '')}\n"
                
            content = MemoryLoader.stringify(data, body)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            logger.info(f"Staging semantic event to {relative_path}")
            
            # ATOMIC COMMIT GUARD with Retries
            try:
                self._run_git(["add", "--", relative_path], cwd=self.repo_path)
                # Use -- <file> to ensure we only commit what we intended, 
                # though git commit with file argument stages it anyway.
                self._run_git(["commit", "-m", f"Add {event.kind}: {event.content[:50]}", "--", relative_path], cwd=self.repo_path)
            except Exception as e:
                if os.path.exists(full_path):
                    os.remove(full_path)
                logger.error(f"Git Transaction Failed for {relative_path}. Error: {str(e)}")
                raise RuntimeError(f"Semantic Transaction Failed: {str(e)}")

            return relative_path
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
            
            self._run_git(["add", "--", filename], cwd=self.repo_path)
            self._run_git(["commit", "-m", commit_msg, "--", filename], cwd=self.repo_path)
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
    