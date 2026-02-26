import os
import yaml
import logging
import sqlite3
import uuid
import threading
from datetime import datetime
from typing import List, Optional, Any, Dict, Tuple
from contextlib import contextmanager
from ledgermind.core.core.schemas import MemoryEvent, TrustBoundary
from ledgermind.core.stores.interfaces import MetadataStore, AuditProvider
from ledgermind.core.stores.audit_git import GitAuditProvider
from ledgermind.core.stores.semantic_store.integrity import IntegrityChecker

from ledgermind.core.stores.semantic_store.transitions import TransitionValidator
from ledgermind.core.stores.semantic_store.loader import MemoryLoader
from ledgermind.core.stores.semantic_store.meta import SemanticMetaStore
from ledgermind.core.stores.semantic_store.transactions import FileSystemLock

# Setup structured logging
logger = logging.getLogger("ledgermind-core.semantic")

class SemanticStore:
    """
    Store for semantic memory (long-term decisions) using a pluggable 
    AuditProvider for versioning and a MetadataStore for indexing.
    """
    def __init__(self, repo_path: str, trust_boundary: TrustBoundary = TrustBoundary.AGENT_WITH_INTENT, 
                 meta_store: Optional[MetadataStore] = None,
                 audit_store: Optional[AuditProvider] = None,
                 skip_validate: bool = False):
        self.repo_path = repo_path
        self.trust_boundary = trust_boundary
        self.lock_file = os.path.join(repo_path, ".lock")
        
        self._fs_lock = FileSystemLock(self.lock_file)
        self._local = threading.local()
        
        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path, exist_ok=True)
            
        self.meta = meta_store or SemanticMetaStore(os.path.join(repo_path, "semantic_meta.db"))
        
        # Check for Git availability
        import subprocess
        git_available = False
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
            git_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        if audit_store:
            self.audit = audit_store
        elif git_available:
            self.audit = GitAuditProvider(repo_path)
        else:
            from ledgermind.core.stores.audit_no import NoAuditProvider
            self.audit = NoAuditProvider(repo_path)
        
        self.audit.initialize()
        
        # Data Format Migration (Ensure backward compatibility)
        self._fs_lock.acquire(exclusive=True)
        try:
            if self.meta.get_version() != "1.22.0":
                from ledgermind.core.core.migration import MigrationEngine
                migrator = MigrationEngine(self)
                migrator.run_all()
                self.meta.set_version("1.22.0")
        finally:
            self._fs_lock.release()
        
        self.reconcile_untracked()
        if not skip_validate:
            IntegrityChecker.validate(self.repo_path)
        self.sync_meta_index()

    def reconcile_untracked(self):
        """Finds files that are on disk but not in audit (Git) and adds them."""
        self._fs_lock.acquire(exclusive=True)
        import subprocess
        try:
            disk_files = []
            for root, _, filenames in os.walk(self.repo_path):
                if ".git" in root or ".tx_backup" in root: continue
                for f in filenames:
                    if f.endswith(".md") or f.endswith(".yaml"):
                        rel_path = os.path.relpath(os.path.join(root, f), self.repo_path)
                        disk_files.append(rel_path)

            for f in disk_files:
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

    def sync_meta_index(self, force: bool = False):
        """Ensures that the metadata index reflects the actual Markdown files on disk."""
        should_lock = not self._in_transaction
        if should_lock: self._fs_lock.acquire(exclusive=True)
        from datetime import datetime
        try:
            # Re-verify integrity if forced
            if force:
                IntegrityChecker.validate(self.repo_path, force=True)

            # 1. Get current files on disk
            disk_files = set()
            for root, _, filenames in os.walk(self.repo_path):
                if ".git" in root or ".tx_backup" in root: continue
                for f in filenames:
                    if f.endswith(".md") or f.endswith(".yaml"):
                        rel_path = os.path.relpath(os.path.join(root, f), self.repo_path)
                        disk_files.add(rel_path)

            # 2. Get current records in MetaStore
            try:
                current_meta = self.meta.list_all()
                meta_files = {m['fid'] for m in current_meta}
            except Exception:
                current_meta = []
                meta_files = set()

            # 3. Handle Mismatches and Updates
            if disk_files != meta_files or force:
                if disk_files != meta_files:
                    logger.info(f"Syncing semantic meta index ({len(disk_files)} on disk, {len(meta_files)} in meta)...")
                
                # Remove orphans from meta
                for orphaned_fid in meta_files - disk_files:
                    logger.debug(f"Removing orphan from meta: {orphaned_fid}")
                    self.meta.delete(orphaned_fid)
                
                # Add/Update missing or changed files
                for f in disk_files:
                    try:
                        full_path = os.path.join(self.repo_path, f)
                        mtime = os.path.getmtime(full_path)
                        
                        existing = self.meta.get_by_fid(f)
                        if existing and not force:
                            # Heuristic: if timestamp in meta is close to mtime, skip re-parsing
                            # A more robust way would be a dedicated 'last_synced_mtime' column
                            existing_ts = existing.get('timestamp')
                            if isinstance(existing_ts, str):
                                try:
                                    from datetime import datetime
                                    existing_ts = datetime.fromisoformat(existing_ts)
                                except ValueError: pass
                            
                            if existing_ts and abs(existing_ts.timestamp() - mtime) < 1.0:
                                continue

                        with open(full_path, 'r', encoding='utf-8') as stream:
                            raw_content = stream.read()
                            data, body = MemoryLoader.parse(raw_content)
                            if data:
                                import json
                                ts = data.get("timestamp")
                                if isinstance(ts, str):
                                    from datetime import datetime
                                    ts = datetime.fromisoformat(ts)
                                
                                # Use file mtime if no internal timestamp
                                final_ts = ts or datetime.fromtimestamp(mtime)
                                
                                sync_ctx = data.get("context", {})
                                sync_target = sync_ctx.get("target") or "unknown"
                                sync_ns = sync_ctx.get("namespace") or "default"
                                sync_keywords = sync_ctx.get("keywords", [])
                                if isinstance(sync_keywords, list):
                                    sync_keywords = ", ".join(sync_keywords)

                                self.meta.upsert(
                                    fid=f, 
                                    target=sync_target,
                                    title=sync_ctx.get("title", "") if sync_ctx else "",
                                    status=sync_ctx.get("status", "unknown") if sync_ctx else "unknown",
                                    kind=data.get("kind", "unknown"),
                                    timestamp=final_ts,
                                    superseded_by=sync_ctx.get("superseded_by") if sync_ctx else None,
                                    namespace=sync_ns,
                                    content=data.get("content", "")[:8000],
                                    keywords=sync_keywords,
                                    confidence=sync_ctx.get("confidence", 1.0) if sync_ctx else 1.0,
                                    context_json=json.dumps(sync_ctx or {})
                                )
                    except Exception as e:
                        logger.error(f"Failed to index {f}: {e}")
        finally:
            if should_lock: self._fs_lock.release()

    @property
    def _in_transaction(self) -> bool:
        return getattr(self._local, 'in_transaction', False)

    @_in_transaction.setter
    def _in_transaction(self, value: bool):
        self._local.in_transaction = value

    @property
    def _current_tx(self) -> Optional[Any]:
        return getattr(self._local, 'current_tx', None)

    @_current_tx.setter
    def _current_tx(self, value: Optional[Any]):
        self._local.current_tx = value

    @contextmanager
    def transaction(self):
        """Groups multiple operations into a single ACID transactional unit using TransactionManager."""
        if self._in_transaction:
            yield
            return

        from ledgermind.core.stores.semantic_store.transactions import TransactionManager
        self._current_tx = TransactionManager(self.repo_path, self.meta)
        self._in_transaction = True
        
        try:
            with self._current_tx.begin():
                yield
                # Invariants check before commit
                IntegrityChecker.validate(self.repo_path)
                
                # Commit to Audit Provider (Git) BEFORE releasing SQLite savepoint
                self.audit.commit_transaction("Atomic Transaction Commit")
        except Exception as e:
            logger.error(f"Transaction Failed: {e}. Rolling back...")
            if isinstance(self.audit, GitAuditProvider):
                self.audit.run(["reset", "--hard", "HEAD"])
            self.sync_meta_index() 
            raise
        finally:
            self._in_transaction = False
            self._current_tx = None

    def _enforce_trust(self, event: Optional[MemoryEvent] = None):
        if self.trust_boundary == TrustBoundary.HUMAN_ONLY:
            if not event or (event.source == "agent" and event.kind == "decision"):
                raise PermissionError("Trust Boundary Violation")

    def _upsert_metadata(self, fid: str, target: str, namespace: str, kind: str,
                         timestamp: datetime, content: str, context: Dict[str, Any],
                         status: str):
        """
        Shared logic for upserting metadata to the store.
        """
        # Prepare cached content including rationale for searchability
        rationale = context.get('rationale', '')
        cached_content = f"{content}\n{rationale}" if rationale else content

        keywords = context.get('keywords', [])
        if isinstance(keywords, list):
            keywords = ", ".join(keywords)

        import json
        try:
            self.meta.upsert(
                fid=fid,
                target=target,
                title=context.get('title', ''),
                status=status,
                kind=kind,
                timestamp=timestamp,
                superseded_by=context.get('superseded_by'),
                namespace=namespace,
                content=cached_content[:8000],
                keywords=keywords,
                confidence=context.get('confidence', 1.0),
                context_json=json.dumps(context)
            )
        except sqlite3.IntegrityError as ie:
            if "UNIQUE" in str(ie):
                msg = f"CONFLICT: Target '{target}' in namespace '{namespace}' already has active decisions."
                logger.warning(msg)
                from ledgermind.core.core.exceptions import ConflictError
                raise ConflictError(msg)
            raise

    def save(self, event: MemoryEvent, namespace: Optional[str] = None) -> str:
        self._enforce_trust(event)
        
        # Security: Validate namespace
        if namespace and namespace != "default":
            import re
            if not re.match(r'^[a-zA-Z0-9_\-]+$', namespace):
                raise ValueError(f"Invalid namespace format: {namespace}. Only alphanumeric, underscores, and hyphens allowed.")
        
        if not self._in_transaction: self._fs_lock.acquire(exclusive=True)
        
        effective_namespace = namespace if namespace and namespace != "default" else None
        
        try:
            suffix = uuid.uuid4().hex[:8]
            filename = f"{event.kind}_{event.timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{suffix}.md"
            relative_path = os.path.join(effective_namespace, filename) if effective_namespace else filename
            full_path = os.path.join(self.repo_path, relative_path)
            
            if self._in_transaction and self._current_tx:
                self._current_tx.stage_file(relative_path)

            if effective_namespace: os.makedirs(os.path.join(self.repo_path, effective_namespace), exist_ok=True)
            
            data = event.model_dump(mode='json')
            body = f"# {event.content}\n\nRecorded from source: {event.source}\n"
            content = MemoryLoader.stringify(data, body)
            
            with open(full_path, "w", encoding="utf-8") as f: 
                f.write(content)
            
            try:
                # Use data['context'] which is guaranteed to be a dict by model_dump above
                ctx_dict = data.get('context', {})
                
                # Determine target and namespace (logic from original code preserved)
                # Note: get_ctx_val logic is simplified because ctx_dict is a dict.
                final_target = ctx_dict.get('target') or 'unknown'
                final_namespace = namespace or ctx_dict.get('namespace') or 'default'

                self._upsert_metadata(
                    fid=relative_path,
                    target=final_target,
                    namespace=final_namespace,
                    kind=event.kind,
                    timestamp=event.timestamp,
                    content=event.content,
                    context=ctx_dict,
                    status=ctx_dict.get('status', 'active')
                )
            except Exception as e:
                # If we are in a transaction, TransactionManager will handle rollback.
                # If not, we do manual cleanup.
                if not self._in_transaction:
                    if os.path.exists(full_path): os.remove(full_path)
                
                if "ConflictError" in str(type(e)): raise
                raise RuntimeError(f"Metadata Update Failed: {e}")

            if not self._in_transaction:
                try:
                    IntegrityChecker.validate(self.repo_path)
                    self.audit.add_artifact(relative_path, content, f"Add {event.kind}: {event.content[:50]}")
                except Exception as e:
                    if os.path.exists(full_path): os.remove(full_path)
                    self.meta.delete(relative_path)
                    raise RuntimeError(f"Integrity Violation: {e}")
            else:
                # In transaction: stage the file for the final atomic commit
                if isinstance(self.audit, GitAuditProvider):
                    self.audit.run(["add", "--", relative_path])
            
            return relative_path
        finally:
            if not self._in_transaction: self._fs_lock.release()

    def _validate_fid(self, fid: str):
        """Prevents Path Traversal attacks."""
        if ".." in fid or fid.startswith("/") or fid.startswith("~"):
            raise ValueError(f"Invalid file identifier: {fid}")

    def update_decision(self, filename: str, updates: dict, commit_msg: str):
        self._validate_fid(filename)
        self._enforce_trust()
        if not self._in_transaction: self._fs_lock.acquire(exclusive=True)
        try:
            if self._in_transaction and self._current_tx:
                self._current_tx.stage_file(filename)

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
            
            final_target_upd = ctx.get("target") or old_data.get("context", {}).get("target") or "unknown"
            final_ns_upd = ctx.get("namespace") or old_data.get("context", {}).get("namespace") or "default"

            try:
                self._upsert_metadata(
                    fid=filename,
                    target=final_target_upd,
                    namespace=final_ns_upd,
                    kind=new_data.get("kind"),
                    timestamp=ts or datetime.now(),
                    content=new_data.get("content", ""),
                    context=ctx,
                    status=ctx.get("status")
                )
            except Exception as e:
                if not self._in_transaction:
                    with open(file_path, "w", encoding="utf-8") as f: f.write(content)
                
                if "ConflictError" in str(type(e)): raise
                raise RuntimeError(f"Metadata Update Failed: {e}")


            if not self._in_transaction:
                try:
                    IntegrityChecker.validate(self.repo_path)
                    self.audit.update_artifact(filename, new_content, commit_msg)
                except Exception as e:
                    with open(file_path, "w", encoding="utf-8") as f: f.write(content)
                    self.sync_meta_index()
                    raise RuntimeError(f"Integrity Violation: {e}")
            else:
                # Inside transaction: just stage the change
                if isinstance(self.audit, GitAuditProvider):
                    self.audit.run(["add", "--", filename])
        finally:
            if not self._in_transaction: self._fs_lock.release()

    def list_decisions(self) -> List[str]:
        should_lock = not self._in_transaction
        if should_lock: self._fs_lock.acquire(exclusive=False)
        try:
            all_meta = self.meta.list_all()
            return [m['fid'] for m in all_meta]
        finally: 
            if should_lock: self._fs_lock.release()

    def purge_memory(self, fid: str):
        """Hard delete for GDPR compliance."""
        should_lock = not self._in_transaction
        if should_lock: self._fs_lock.acquire(exclusive=True)
        try:
            full_path = os.path.join(self.repo_path, fid)
            if os.path.exists(full_path): os.remove(full_path)
            self.audit.purge_artifact(fid)
            self.meta.delete(fid)
        finally: 
            if should_lock: self._fs_lock.release()

    def get_head_hash(self) -> Optional[str]:
        return self.audit.get_head_hash()

    def list_active_conflicts(self, target: str, namespace: str = "default") -> List[str]:
        should_lock = not self._in_transaction
        if should_lock: self._fs_lock.acquire(exclusive=False)
        try:
            all_meta = self.meta.list_all()
            return [m['fid'] for m in all_meta if m.get('target') == target and m.get('status') == 'active' and m.get('kind') == 'decision' and m.get('namespace', 'default') == namespace]
        finally: 
            if should_lock: self._fs_lock.release()
