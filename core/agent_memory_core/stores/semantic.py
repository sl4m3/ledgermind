import os
import yaml
import logging
import sqlite3
import uuid
from typing import List, Optional, Any, Dict, Tuple
from contextlib import contextmanager
from agent_memory_core.core.schemas import MemoryEvent, TrustBoundary
from agent_memory_core.stores.interfaces import MetadataStore, AuditProvider
from agent_memory_core.stores.audit_git import GitAuditProvider
from agent_memory_core.core.telemetry import update_decision_metrics, GIT_COMMIT_SIZE
from agent_memory_core.stores.semantic_store.integrity import IntegrityChecker
from agent_memory_core.stores.semantic_store.transitions import TransitionValidator
from agent_memory_core.stores.semantic_store.loader import MemoryLoader
from agent_memory_core.stores.semantic_store.meta import SemanticMetaStore
from agent_memory_core.stores.semantic_store.transactions import FileSystemLock

# Setup structured logging
logger = logging.getLogger("agent-memory-core.semantic")

class SemanticStore:
    """
    Store for semantic memory (long-term decisions) using a pluggable 
    AuditProvider for versioning and a MetadataStore for indexing.
    """
    def __init__(self, repo_path: str, trust_boundary: TrustBoundary = TrustBoundary.AGENT_WITH_INTENT, 
                 meta_store: Optional[MetadataStore] = None,
                 audit_store: Optional[AuditProvider] = None):
        self.repo_path = repo_path
        self.trust_boundary = trust_boundary
        self.lock_file = os.path.join(repo_path, ".lock")
        
        self._fs_lock = FileSystemLock(self.lock_file)
        self._in_transaction = False
        
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path, exist_ok=True)
            
        self.meta = meta_store or SemanticMetaStore(os.path.join(repo_path, "semantic_meta.db"))
        self.audit = audit_store or GitAuditProvider(repo_path)
        
        self.audit.initialize()
        
        # Data Format Migration (Ensure backward compatibility)
        from agent_memory_core.core.migration import MigrationEngine
        migrator = MigrationEngine(self)
        migrator.run_all()
        
        self.reconcile_untracked()
        self.sync_meta_index()
        IntegrityChecker.validate(self.repo_path)

    def reconcile_untracked(self):
        """Finds files that are on disk but not in audit (Git) and adds them."""
        self._fs_lock.acquire(exclusive=True)
        import subprocess
        try:
            files = [f for f in os.listdir(self.repo_path) if f.endswith(".md") or f.endswith(".yaml")]
            for f in files:
                # Check if file is tracked by git
                if isinstance(self.audit, GitAuditProvider):
                    res = subprocess.run(["git", "ls-files", "--error-unmatch", f], 
                                         cwd=self.repo_path, capture_output=True)
                    if res.returncode != 0:
                        logger.info(f"Recovering untracked file: {f}")
                        try:
                            with open(os.path.join(self.repo_path, f), 'r', encoding='utf-8') as stream:
                                content = stream.read()
                            self.audit.add_artifact(f, content, f"Recovery: Auto-adding untracked file {f}")
                        except Exception as e:
                            logger.error(f"Failed to recover {f}: {e}")
        finally:
            self._fs_lock.release()

    def sync_meta_index(self):
        """Ensures that the metadata index reflects the actual Markdown files on disk."""
        self._fs_lock.acquire(exclusive=False)
        from datetime import datetime
        try:
            files = [f for f in os.listdir(self.repo_path) if f.endswith(".md") or f.endswith(".yaml")]
            try:
                current_meta = self.meta.list_all()
            except Exception:
                # Fallback or initialization
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
                                    superseded_by=ctx.get("superseded_by"),
                                    namespace=ctx.get("namespace", "default")
                                )
                    except Exception as e:
                        logger.error(f"Failed to index {f}: {e}")
        finally:
            self._fs_lock.release()

    @contextmanager
    def transaction(self):
        """Groups multiple operations into a single ACID transactional unit."""
        self._fs_lock.acquire(exclusive=True)
        self._in_transaction = True
        
        import shutil
        backup_dir = os.path.join(self.repo_path, ".tx_backup")
        if os.path.exists(backup_dir): shutil.rmtree(backup_dir)
        os.makedirs(backup_dir)

        try:
            yield
            IntegrityChecker.validate(self.repo_path, force=True)
            self.audit.commit_transaction("Atomic Transaction Commit")
        except Exception as e:
            logger.error(f"Transaction Failed: {e}. Rolling back...")
            # Basic Git-level rollback for GitAuditProvider
            if isinstance(self.audit, GitAuditProvider):
                self.audit._run_git(["reset", "--hard", "HEAD"])
            self.sync_meta_index() 
            raise
        finally:
            self._in_transaction = False
            if os.path.exists(backup_dir): shutil.rmtree(backup_dir)
            self._fs_lock.release()

    def _enforce_trust(self, event: Optional[MemoryEvent] = None):
        if self.trust_boundary == TrustBoundary.HUMAN_ONLY:
            if not event or (event.source == "agent" and event.kind == "decision"):
                raise PermissionError("Trust Boundary Violation")

    def save(self, event: MemoryEvent, namespace: Optional[str] = None) -> str:
        self._enforce_trust(event)
        if not self._in_transaction: self._fs_lock.acquire(exclusive=True)
        
        effective_namespace = namespace if namespace and namespace != "default" else None
        
        try:
            suffix = uuid.uuid4().hex[:8]
            filename = f"{event.kind}_{event.timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{suffix}.md"
            relative_path = os.path.join(effective_namespace, filename) if effective_namespace else filename
            full_path = os.path.join(self.repo_path, relative_path)
            
            if effective_namespace: os.makedirs(os.path.join(self.repo_path, effective_namespace), exist_ok=True)
            
            data = event.model_dump(mode='json')
            body = f"# {event.content}\n\nRecorded from source: {event.source}\n"
            content = MemoryLoader.stringify(data, body)
            
            with open(full_path, "w", encoding="utf-8") as f: 
                f.write(content)
                GIT_COMMIT_SIZE.observe(len(content))
            
            try:
                ctx = event.context
                self.meta.upsert(
                    fid=relative_path,
                    target=ctx.target if hasattr(ctx, 'target') else ctx.get('target'),
                    status=ctx.status if hasattr(ctx, 'status') else ctx.get('status', 'active'),
                    kind=event.kind,
                    timestamp=event.timestamp,
                    namespace=namespace or "default"
                )
                update_decision_metrics(self.meta)
            except Exception as e:
                if os.path.exists(full_path): os.remove(full_path)
                raise RuntimeError(f"Metadata Update Failed: {e}")

            if not self._in_transaction:
                try:
                    IntegrityChecker.validate(self.repo_path, force=True)
                    self.audit.add_artifact(relative_path, content, f"Add {event.kind}: {event.content[:50]}")
                except Exception as e:
                    if os.path.exists(full_path): os.remove(full_path)
                    self.meta.delete(relative_path)
                    raise RuntimeError(f"Integrity Violation: {e}")
            else:
                if isinstance(self.audit, GitAuditProvider):
                    self.audit._run_git(["add", "--", relative_path])
            
            return relative_path
        finally:
            if not self._in_transaction: self._fs_lock.release()

    def update_decision(self, filename: str, updates: dict, commit_msg: str):
        self._enforce_trust()
        if not self._in_transaction: self._fs_lock.acquire(exclusive=True)
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
            
            ctx = new_data.get("context", {})
            from datetime import datetime
            ts = new_data.get("timestamp")
            if isinstance(ts, str): ts = datetime.fromisoformat(ts)
            self.meta.upsert(
                fid=filename,
                target=ctx.get("target"),
                status=ctx.get("status"),
                kind=new_data.get("kind"),
                timestamp=ts or datetime.now(),
                superseded_by=ctx.get("superseded_by"),
                namespace=ctx.get("namespace", "default")
            )

            if not self._in_transaction:
                try:
                    IntegrityChecker.validate(self.repo_path, force=True)
                    self.audit.update_artifact(filename, new_content, commit_msg)
                except Exception as e:
                    with open(file_path, "w", encoding="utf-8") as f: f.write(content)
                    self.sync_meta_index()
                    raise RuntimeError(f"Integrity Violation: {e}")
            else:
                if isinstance(self.audit, GitAuditProvider):
                    self.audit._run_git(["add", "--", filename])
        finally:
            if not self._in_transaction: self._fs_lock.release()

    def list_decisions(self) -> List[str]:
        self._fs_lock.acquire(exclusive=False)
        try:
            all_meta = self.meta.list_all()
            return [m['fid'] for m in all_meta]
        finally: self._fs_lock.release()

    def purge_memory(self, fid: str):
        """Hard delete for GDPR compliance."""
        self._fs_lock.acquire(exclusive=True)
        try:
            full_path = os.path.join(self.repo_path, fid)
            if os.path.exists(full_path): os.remove(full_path)
            self.audit.purge_artifact(fid)
            self.meta.delete(fid)
        finally: self._fs_lock.release()

    def get_head_hash(self) -> Optional[str]:
        return self.audit.get_head_hash()

    def list_active_conflicts(self, target: str, namespace: str = "default") -> List[str]:
        self._fs_lock.acquire(exclusive=False)
        try:
            all_meta = self.meta.list_all()
            return [m['fid'] for m in all_meta if m.get('target') == target and m.get('status') == 'active' and m.get('kind') == 'decision' and m.get('namespace', 'default') == namespace]
        finally: self._fs_lock.release()
