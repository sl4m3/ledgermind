import os
import subprocess
import yaml
import time
import logging
import sqlite3
import uuid
from typing import List, Optional, Any, Dict
from contextlib import contextmanager
from agent_memory_core.core.schemas import MemoryEvent, TrustBoundary
from agent_memory_core.stores.semantic_store.integrity import IntegrityChecker, IntegrityViolation
from agent_memory_core.stores.semantic_store.transitions import TransitionValidator
from agent_memory_core.stores.semantic_store.loader import MemoryLoader
from agent_memory_core.stores.semantic_store.meta import SemanticMetaStore

# Setup structured logging
logger = logging.getLogger("agent-memory-core.semantic")

class SemanticStore:
    """
    Store for semantic memory (long-term decisions) using Git for versioning
    and SQLite for transactional metadata indexing.
    """
    def __init__(self, repo_path: str, trust_boundary: TrustBoundary = TrustBoundary.AGENT_WITH_INTENT):
        """
        Initialize the semantic store.
        """
        self.repo_path = repo_path
        self.trust_boundary = trust_boundary
        self.lock_file = os.path.join(repo_path, ".lock")
        self.meta_db_path = os.path.join(repo_path, "semantic_meta.db")
        self._lock_handle = None
        self._in_transaction = False
        
        # Ensure directory exists before DB init
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path, exist_ok=True)
            
        self.meta = SemanticMetaStore(self.meta_db_path)
        self._init_repo()
        self._recover_dirty_state()
        
        # Sync SQLite index with Git on startup
        self.sync_meta_index()
        
        # Final validation of the whole state
        IntegrityChecker.validate(self.repo_path)

    def sync_meta_index(self):
        """Ensures that the SQLite index reflects the actual Markdown files on disk."""
        self._acquire_lock(shared=False)
        from datetime import datetime
        try:
            files = [f for f in os.listdir(self.repo_path) if f.endswith(".md") or f.endswith(".yaml")]
            try:
                current_meta = self.meta.list_all()
            except sqlite3.OperationalError:
                # Table might not exist if DB was corrupted or init failed
                self.meta._init_db()
                current_meta = []

            if len(files) != len(current_meta):
                logger.info("Rebuilding semantic meta index...")
                self.meta.clear()
                for f in files:
                    try:
                        with open(os.path.join(self.repo_path, f), 'r', encoding='utf-8') as stream:
                            data, _ = MemoryLoader.parse(stream.read())
                            if data:
                                ctx = data.get("context", {})
                                ts = data.get("timestamp")
                                if isinstance(ts, str): ts = datetime.fromisoformat(ts)
                                self.meta.upsert(
                                    fid=f, 
                                    target=ctx.get("target", "unknown"),
                                    status=ctx.get("status", "unknown"),
                                    kind=data.get("kind", "unknown"),
                                    timestamp=ts or datetime.now(),
                                    superseded_by=ctx.get("superseded_by")
                                )
                    except Exception as e:
                        logger.error(f"Failed to index {f}: {e}")
        finally:
            self._release_lock()

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
        self._acquire_lock(shared=False)
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
                    if f.startswith(".") or f == ".lock": continue
                        
                    full_f = os.path.join(self.repo_path, f)
                    is_valid = False
                    if f.endswith(".md"):
                        try:
                            with open(full_f, 'r', encoding='utf-8') as file:
                                MemoryLoader.parse(file.read())
                            is_valid = True
                        except Exception: is_valid = False
                    
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

    def _acquire_lock(self, shared: bool = False):
        if self._lock_handle: return
            
        timeout = 15 
        start_time = time.time()
        
        if not os.path.exists(self.lock_file):
            try:
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL)
                os.close(fd)
            except FileExistsError: pass

        while True:
            try:
                # Keep file handle open to maintain lock
                h = open(self.lock_file, 'w')
                try:
                    import fcntl
                    lock_type = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
                    # This will raise BlockingIOError if lock is held by another process
                    fcntl.flock(h, lock_type | fcntl.LOCK_NB)
                except (ImportError, AttributeError):
                    # Fallback for systems without fcntl support
                    pass
                except (OSError, IOError) as e:
                    # Lock is held by someone else, retry
                    h.close()
                    if time.time() - start_time > timeout:
                        mode = "shared" if shared else "exclusive"
                        raise TimeoutError(f"Could not acquire {mode} lock after {timeout}s: {e}")
                    time.sleep(0.1)
                    continue
                
                self._lock_handle = h
                self._lock_handle.write(str(os.getpid()))
                self._lock_handle.flush()
                return
            except (OSError, IOError) as e:
                # Error opening the file, retry
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Lock file access error after {timeout}s: {e}")
                time.sleep(0.1)

    def _release_lock(self):
        if self._lock_handle:
            try:
                try:
                    import fcntl
                    fcntl.flock(self._lock_handle, fcntl.LOCK_UN)
                except (ImportError, AttributeError, OSError): pass
                self._lock_handle.close()
            except Exception: pass
            self._lock_handle = None

    @contextmanager
    def transaction(self):
        """
        Groups multiple operations into a single transactional unit with deferred validation.
        """
        self._acquire_lock(shared=False)
        self._in_transaction = True
        try:
            yield
            # Validate final state
            IntegrityChecker.validate(self.repo_path, force=True)
            # Commit everything that was staged
            self._run_git(["commit", "-m", "Atomic Transaction Commit", "--"], cwd=self.repo_path)
        except Exception as e:
            logger.error(f"Transaction Failed: {e}")
            self._run_git(["reset", "--hard", "HEAD"], cwd=self.repo_path)
            raise
        finally:
            self._in_transaction = False
            self._release_lock()

    def _enforce_trust(self, event: Optional[MemoryEvent] = None):
        if self.trust_boundary == TrustBoundary.HUMAN_ONLY:
            if not event or (event.source == "agent" and event.kind == "decision"):
                raise PermissionError("Trust Boundary Violation")

    def _run_git(self, args: List[str], cwd: str, max_retries: int = 15):
        last_error = ""
        for i in range(max_retries):
            try:
                return subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True)
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

    def get_head_hash(self) -> Optional[str]:
        """Returns the current Git HEAD hash."""
        try:
            res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo_path, capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception: pass
        return None

    def save(self, event: MemoryEvent, namespace: Optional[str] = None) -> str:
        self._enforce_trust(event)
        if not self._in_transaction: self._acquire_lock(shared=False)
        
        try:
            suffix = uuid.uuid4().hex[:8]
            filename = f"{event.kind}_{event.timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{suffix}.md"
            relative_path = os.path.join(namespace, filename) if namespace else filename
            full_path = os.path.join(self.repo_path, relative_path)
            
            if namespace: os.makedirs(os.path.join(self.repo_path, namespace), exist_ok=True)
            
            data = event.model_dump(mode='json')
            body = f"# {event.content}\n\nRecorded from source: {event.source}\n"
            content = MemoryLoader.stringify(data, body)
            
            with open(full_path, "w", encoding="utf-8") as f: f.write(content)
            
            # ATOMIC METADATA UPDATE: Prevents I4 violations via SQLite Unique Constraint
            try:
                ctx = event.context
                self.meta.upsert(
                    fid=filename,
                    target=ctx.target if hasattr(ctx, 'target') else ctx.get('target'),
                    status=ctx.status if hasattr(ctx, 'status') else ctx.get('status', 'active'),
                    kind=event.kind,
                    timestamp=event.timestamp
                )
            except sqlite3.IntegrityError as e:
                if os.path.exists(full_path): os.remove(full_path)
                if "idx_active_target" in str(e):
                    raise RuntimeError(f"Conflict: Target already has an active decision. Use 'supersede'.")
                raise

            self._run_git(["add", "--", relative_path], cwd=self.repo_path)

            if not self._in_transaction:
                try:
                    IntegrityChecker.validate(self.repo_path, force=True)
                    self._run_git(["commit", "-m", f"Add {event.kind}: {event.content[:50]}", "--", relative_path], cwd=self.repo_path)
                except Exception as e:
                    if os.path.exists(full_path): os.remove(full_path)
                    self.meta.delete(filename)
                    raise RuntimeError(f"Integrity Violation: {e}")
            return relative_path
        finally:
            if not self._in_transaction: self._release_lock()

    def update_decision(self, filename: str, updates: dict, commit_msg: str):
        self._enforce_trust()
        if not self._in_transaction: self._acquire_lock(shared=False)
        try:
            file_path = os.path.join(self.repo_path, filename)
            with open(file_path, "r", encoding="utf-8") as f: content = f.read()
            old_data, body = MemoryLoader.parse(content)
            new_data = yaml.safe_load(yaml.dump(old_data))
            if "context" not in new_data: new_data["context"] = {}
            new_data["context"].update(updates)
            TransitionValidator.validate_update(old_data, new_data)
            
            new_content = MemoryLoader.stringify(new_data, body)
            with open(file_path, "w", encoding="utf-8") as f: f.write(new_content)
            
            # Sync metadata to SQLite
            from datetime import datetime
            ctx = new_data.get("context", {})
            ts = new_data.get("timestamp")
            if isinstance(ts, str): ts = datetime.fromisoformat(ts)
            self.meta.upsert(
                fid=filename,
                target=ctx.get("target"),
                status=ctx.get("status"),
                kind=new_data.get("kind"),
                timestamp=ts or datetime.now(),
                superseded_by=ctx.get("superseded_by")
            )

            self._run_git(["add", "--", filename], cwd=self.repo_path)

            if not self._in_transaction:
                try:
                    IntegrityChecker.validate(self.repo_path, force=True)
                    self._run_git(["commit", "-m", commit_msg, "--", filename], cwd=self.repo_path)
                except Exception as e:
                    with open(file_path, "w", encoding="utf-8") as f: f.write(content)
                    self.sync_meta_index()
                    raise RuntimeError(f"Integrity Violation: {e}")
        finally:
            if not self._in_transaction: self._release_lock()

    def list_decisions(self) -> List[str]:
        self._acquire_lock(shared=True)
        try:
            return [f for f in os.listdir(self.repo_path) if f.endswith(".md") or f.endswith(".yaml")]
        finally: self._release_lock()
    
    def list_active_conflicts(self, target: str) -> List[str]:
        self._acquire_lock(shared=True)
        try:
            conflicts = []
            for filename in self.list_decisions():
                try:
                    with open(os.path.join(self.repo_path, filename), 'r', encoding='utf-8') as f:
                        data, _ = MemoryLoader.parse(f.read())
                        ctx = data.get("context", {})
                        if (data.get("kind") == "decision" and ctx.get("target") == target and ctx.get("status") == "active"):
                            conflicts.append(filename)
                except Exception: continue
            return conflicts
        finally: self._release_lock()
    
    def find_proposal(self, target: str) -> Optional[str]:
        self._acquire_lock(shared=True)
        try:
            for filename in self.list_decisions():
                try:
                    with open(os.path.join(self.repo_path, filename), 'r', encoding='utf-8') as f:
                        data, _ = MemoryLoader.parse(f.read())
                        ctx = data.get("context", {})
                        if (data.get("kind") == "proposal" and ctx.get("target") == target and ctx.get("status") == "draft"):
                            return filename
                except Exception: continue
            return None
        finally: self._release_lock()
