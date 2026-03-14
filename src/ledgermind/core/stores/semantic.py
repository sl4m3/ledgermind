import os
import re
import yaml
import json
import logging
import sqlite3
import uuid
import threading
import subprocess
from datetime import datetime
from typing import List, Optional, Any, Dict, Tuple
from contextlib import contextmanager, nullcontext
from ledgermind.core.core.schemas import MemoryEvent, TrustBoundary
from ledgermind.core.stores.interfaces import MetadataStore, AuditProvider
from ledgermind.core.stores.audit_git import GitAuditProvider
from ledgermind.core.stores.audit_no import NoAuditProvider
from ledgermind.core.core.migration import MigrationEngine
from ledgermind.core.core.exceptions import ConflictError
from ledgermind.core.stores.semantic_store.integrity import IntegrityChecker
from ledgermind.core.stores.semantic_store.transitions import TransitionValidator
from ledgermind.core.stores.semantic_store.loader import MemoryLoader
from ledgermind.core.stores.semantic_store.meta import SemanticMetaStore
from ledgermind.core.stores.semantic_store.transactions import FileSystemLock, TransactionManager

# Setup structured logging
logger = logging.getLogger("ledgermind-core.semantic")

import functools

@functools.lru_cache(maxsize=1024)
def _cached_validate_fid(repo_path_str: str, fid: str) -> str:
    from pathlib import Path

    # ===== LAYER 1: Reject obviously dangerous patterns FIRST =====
    if "\x00" in fid:
        raise ValueError(f"Invalid file identifier (null bytes detected): {fid}")
    if ".." in fid:
        raise ValueError(f"Invalid file identifier (parent directory traversal detected): {fid}")
    if fid.startswith("/") or fid.startswith("\\"):
        raise ValueError(f"Invalid file identifier (absolute path not allowed): {fid}")
    if fid.startswith("~") or fid.startswith("$HOME"):
        raise ValueError(f"Invalid file identifier (home directory expansion blocked): {fid}")

    # ===== LAYER 2: Canonicalize BOTH paths BEFORE comparison =====
    try:
        repo_path = Path(repo_path_str)
        resolved_repo = repo_path.resolve()
        fid_path = repo_path / fid
        resolved_fid = fid_path.resolve()
    except (OSError, ValueError) as e:
        raise ValueError(f"Invalid path resolution for '{fid}': {e}")

    # ===== LAYER 3: Check containment AFTER canonicalization =====
    try:
        resolved_fid.relative_to(resolved_repo)
    except ValueError:
        raise ValueError(f"Invalid file identifier (path outside repository): {fid}")

    # ===== LAYER 4: Final safety checks =====
    fid_str = str(resolved_fid)
    repo_str = str(resolved_repo)
    if not fid_str.startswith(repo_str):
        raise ValueError(f"Invalid file identifier (canonicalized path outside repository): {fid}")
    if any(x in fid_str for x in ["../", "..\\", "\x00"]):
        raise ValueError(f"Invalid file identifier (suspicious pattern in canonicalized path): {fid}")

    return os.path.relpath(fid_str, repo_str)

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
        
        git_available = False
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True) # nosec B603 B607
            git_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        if audit_store:
            self.audit = audit_store
        elif git_available:
            self.audit = GitAuditProvider(repo_path)
        else:
            self.audit = NoAuditProvider(repo_path)
        
        self.audit.initialize()
        
        self._fs_lock.acquire(exclusive=True)
        try:
            if self.meta.get_version() != "1.22.0":
                migrator = MigrationEngine(self)
                migrator.run_all()
                self.meta.set_version("1.22.0")
        finally:
            self._fs_lock.release()

        self.reconcile_untracked()
        self.sync_meta_index()
        if not skip_validate:
            IntegrityChecker.validate(self.repo_path, meta_store=self.meta)

    def reconcile_untracked(self):
        self._fs_lock.acquire(exclusive=True)
        try:
            disk_files = []
            for root, _, filenames in os.walk(self.repo_path):
                if ".git" in root or ".tx_backup" in root: continue
                for f in filenames:
                    if f.endswith(".md") or f.endswith(".yaml"):
                        rel_path = os.path.relpath(os.path.join(root, f), self.repo_path)
                        disk_files.append(rel_path)

            for f in disk_files:
                if isinstance(self.audit, GitAuditProvider):
                    res = subprocess.run(["git", "ls-files", "--error-unmatch", f], 
                                         cwd=self.repo_path, capture_output=True) # nosec B603 B607
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

    def _get_disk_files(self) -> set[str]:
        disk_files = set()
        for root, _, filenames in os.walk(self.repo_path):
            if ".git" in root or ".tx_backup" in root: continue
            for f in filenames:
                if f.endswith(".md") or f.endswith(".yaml"):
                    rel_path = os.path.relpath(os.path.join(root, f), self.repo_path)
                    disk_files.add(rel_path)
        return disk_files

    def _get_meta_files(self) -> set[str]:
        try:
            current_meta = self.meta.list_all()
            return {m['fid'] for m in current_meta}
        except Exception:
            return set()

    def _remove_orphans(self, orphans: set[str]):
        for orphaned_fid in orphans:
            self.meta.delete(orphaned_fid)

    def _update_meta_for_file(self, fid: str, force: bool = False, link_data: Optional[Tuple[int, float]] = None):
        try:
            full_path = os.path.join(self.repo_path, fid)
            mtime = os.path.getmtime(full_path)
            existing = self.meta.get_by_fid(fid)
            with open(full_path, 'r', encoding='utf-8') as stream:
                raw_content = stream.read()

            import hashlib
            h = hashlib.sha256()
            h.update(raw_content.encode('utf-8'))
            current_hash = h.hexdigest()

            if existing and not force:
                if existing.get('content_hash') == current_hash:
                    return

            data, body = MemoryLoader.parse(raw_content)
            if data:
                ts = data.get("timestamp")
                if isinstance(ts, str): ts = datetime.fromisoformat(ts)
                final_ts = ts or datetime.fromtimestamp(mtime)

                sync_ctx = data.get("context", {})
                sync_target = sync_ctx.get("target") or "unknown"
                sync_ns = sync_ctx.get("namespace") or "default"
                sync_keywords = sync_ctx.get("keywords", [])
                if isinstance(sync_keywords, list): sync_keywords = ", ".join(sync_keywords)

                link_c, link_s = 0, 0.0
                if link_data is not None:
                    # Unpack properly, handling edge case where it might be malformed
                    if isinstance(link_data, (tuple, list)) and len(link_data) >= 2:
                        link_c, link_s = link_data[0], link_data[1]
                else:
                    try: link_c, link_s = self.episodic.count_links_for_semantic(fid)
                    except Exception: pass

                final_status = data.get("status") or sync_ctx.get("status", "unknown")
                final_kind = data.get("kind") or sync_ctx.get("kind", "unknown")
                final_supersedes = data.get("supersedes") or sync_ctx.get("supersedes", [])
                final_superseded = data.get("superseded_by") or sync_ctx.get("superseded_by")
                final_merge_status = data.get("merge_status") or sync_ctx.get("merge_status", "idle")
                final_enrichment_status = data.get("enrichment_status") or sync_ctx.get("enrichment_status", "pending")
                final_converted_to = data.get("converted_to") or sync_ctx.get("converted_to")

                self.meta.upsert(
                    fid=fid,
                    target=sync_target,
                    title=sync_ctx.get("title", "") if sync_ctx else "",
                    status=final_status,
                    kind=final_kind,
                    timestamp=final_ts,
                    supersedes=final_supersedes,
                    superseded_by=final_superseded,
                    converted_to=final_converted_to,
                    merge_status=final_merge_status,
                    namespace=sync_ns,
                    content=data.get("content", "")[:8000],
                    keywords=sync_keywords,
                    confidence=sync_ctx.get("confidence", 0.0) if sync_ctx else 0.0,
                    content_hash=current_hash,
                    compressive_rationale=sync_ctx.get("compressive_rationale"),
                    context_json=json.dumps(sync_ctx or {}),
                    phase=sync_ctx.get("phase", existing.get('phase', 'pattern') if existing else 'pattern'),
                    vitality=sync_ctx.get("vitality", existing.get('vitality', 'active') if existing else 'active'),
                    reinforcement_density=sync_ctx.get("reinforcement_density", 0.0),
                    stability_score=sync_ctx.get("stability_score", 0.0),
                    coverage=sync_ctx.get("coverage", 0.0),
                    link_count=link_c,
                    enrichment_status=final_enrichment_status
                )
        except Exception as e:
            logger.error(f"Failed to index {fid}: {e}")

    def sync_meta_index(self, force: bool = False, read_only: bool = False):
        """
        Синхронизировать meta индекс с файловой системой.
        
        force: Если True, запустить IntegrityChecker
        read_only: Если True, использовать shared lock (не блокирует чтение другими)
        """
        should_lock = not self._in_transaction
        if should_lock: 
            # Для read_only использовать shared lock (не эксклюзивный)
            self._fs_lock.acquire(exclusive=not read_only)
        try:
            if force: IntegrityChecker.validate(self.repo_path, force=True)
            disk_files = self._get_disk_files()
            meta_files = self._get_meta_files()
            orphans = meta_files - disk_files
            if orphans:
                logger.info(f"Removing {len(orphans)} orphan records from meta index.")
                self._remove_orphans(orphans)

            # ⚡ Bolt: Prevent N+1 query problem by batch-fetching link counts
            link_counts_batch = {}
            if disk_files and hasattr(self, 'episodic') and hasattr(self.episodic, 'count_links_for_semantic_batch'):
                try:
                    link_counts_batch = self.episodic.count_links_for_semantic_batch(list(disk_files))
                except Exception as e:
                    logger.warning(f"Failed to batch-fetch link counts: {e}")

            cm = self.meta.batch_update() if not self._in_transaction else nullcontext()
            with cm:
                for f in disk_files:
                    link_data = link_counts_batch.get(f)
                    self._update_meta_for_file(f, force=force, link_data=link_data)
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
        if self._in_transaction:
            yield
            return
        self._current_tx = TransactionManager(self.repo_path, self.meta)
        self._in_transaction = True
        try:
            with self._current_tx.begin():
                yield
                IntegrityChecker.validate(self.repo_path, meta_store=self.meta)
                self.audit.commit_transaction("Atomic Transaction Commit")
        except Exception as e:
            logger.error(f"Transaction Failed: {e}. Rolling back...")
            if isinstance(self.audit, GitAuditProvider):
                self.audit.run(["reset", "--hard", "HEAD"])
                self.audit.run(["clean", "-fd"])
            self._in_transaction = False
            self._current_tx = None
            try: self.sync_meta_index() 
            except Exception as se: logger.error(f"Post-rollback synchronization failed: {se}")
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
                         status: str, title: Optional[str] = None, 
                         content_hash: Optional[str] = None,
                         supersedes: Optional[List[str]] = None,
                         superseded_by: Optional[str] = None,
                         merge_status: Optional[str] = None,
                         enrichment_status: Optional[str] = None,
                         converted_to: Optional[str] = None):
        rationale = context.get('rationale', '')
        cached_content = f"{content}\n{rationale}" if rationale else content
        existing = self.meta.get_by_fid(fid)
        final_merge_status = merge_status or (existing.get('merge_status') if existing else "idle")
        final_enrichment_status = enrichment_status or (existing.get('enrichment_status') if existing else "pending")

        if supersedes is None:
            raw_s = existing.get('supersedes') if existing else None
            supersedes = context.get('supersedes') or (json.loads(raw_s) if raw_s else [])
        if superseded_by is None: superseded_by = context.get('superseded_by')
        if converted_to is None: converted_to = context.get('converted_to')

        keywords = context.get('keywords', [])
        if isinstance(keywords, list): keywords = ", ".join(keywords)
        final_title = title or context.get('title') or (existing.get('title') if existing else 'Untitled Decision')
        final_hash = content_hash or (existing.get('content_hash') if existing else None)
        if not final_hash:
            import hashlib
            h = hashlib.sha256()
            h.update(cached_content.encode('utf-8'))
            final_hash = h.hexdigest()

        try:
            self.meta.upsert(
                fid=fid, target=target, title=final_title, status=status, kind=kind,
                timestamp=timestamp, supersedes=supersedes, superseded_by=superseded_by,
                converted_to=converted_to, merge_status=final_merge_status, namespace=namespace,
                content=cached_content[:8000], keywords=keywords, confidence=context.get('confidence', 0.0),
                content_hash=final_hash, last_hit_at=context.get('last_hit_at'),
                compressive_rationale=context.get('compressive_rationale'),
                context_json=json.dumps(context),
                phase=context.get('phase', 'pattern'),
                vitality=context.get('vitality', 'active'),
                reinforcement_density=context.get('reinforcement_density', 0.0),
                stability_score=context.get('stability_score', 0.0),
                coverage=context.get('coverage', 0.0),
                estimated_removal_cost=context.get('estimated_removal_cost', 0.0),
                estimated_utility=context.get('estimated_utility', 0.0),
                enrichment_status=final_enrichment_status
            )
            if not self._in_transaction and hasattr(self.meta, '_conn'):
                self.meta._conn.commit()
        except sqlite3.IntegrityError as ie:
            if "UNIQUE" in str(ie):
                msg = f"CONFLICT: Target '{target}' in namespace '{namespace}' already has active decisions."
                raise ConflictError(msg)
            raise

    def save(self, event: MemoryEvent, namespace: Optional[str] = None) -> str:
        self._enforce_trust(event)
        if namespace and namespace != "default" and not re.match(r'^[a-zA-Z0-9_\-]+$', namespace):
            raise ValueError(f"Invalid namespace: {namespace}")
        if not self._in_transaction: self._fs_lock.acquire(exclusive=True)
        effective_namespace = namespace if namespace and namespace != "default" else None
        try:
            suffix = uuid.uuid4().hex[:8]
            filename = f"{event.kind}_{event.timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{suffix}.md"
            relative_path = os.path.join(effective_namespace, filename) if effective_namespace else filename
            full_path = os.path.join(self.repo_path, relative_path)
            if self._in_transaction and self._current_tx: self._current_tx.stage_file(relative_path)
            if effective_namespace: os.makedirs(os.path.join(self.repo_path, effective_namespace), exist_ok=True)

            data = event.model_dump(mode='json')
            CORE_FIELDS = ["status", "kind", "supersedes", "superseded_by", "merge_status", "enrichment_status", "timestamp", "fid", "source", "content"]
            if "context" in data and isinstance(data["context"], dict):
                for field in CORE_FIELDS:
                    if field in data["context"]: data[field] = data["context"].pop(field)

            body = f"# {event.content}\n\nRecorded from source: {event.source}\n"
            full_file_content = MemoryLoader.stringify(data, body)
            import hashlib
            h = hashlib.sha256()
            h.update(full_file_content.encode('utf-8'))
            final_hash = h.hexdigest()
            with open(full_path, "w", encoding="utf-8") as f: f.write(full_file_content)
            
            ctx_dict = data.get('context', {})
            final_target = ctx_dict.get('target') or 'unknown'
            final_namespace = namespace or ctx_dict.get('namespace') or 'default'
            self._upsert_metadata(
                fid=relative_path, target=final_target, namespace=final_namespace,
                kind=event.kind, timestamp=event.timestamp, content=event.content, context=ctx_dict,
                status=data.get('status') or getattr(event.context, 'status', 'draft'),
                title=data.get('title'), content_hash=final_hash,
                supersedes=data.get('supersedes'), superseded_by=data.get('superseded_by'),
                merge_status=data.get('merge_status'), enrichment_status=data.get('enrichment_status')
            )
            if not self._in_transaction:
                try:
                    IntegrityChecker.validate(self.repo_path, fid=relative_path, data=data, meta_store=self.meta)
                    self.audit.add_artifact(relative_path, full_file_content, f"Add {event.kind}: {event.content[:50]}")
                except Exception as e:
                    if os.path.exists(full_path): os.remove(full_path)
                    self.meta.delete(relative_path)
                    raise e
            elif isinstance(self.audit, GitAuditProvider):
                self.audit.run(["add", "--", relative_path])
            return relative_path
        finally:
            if not self._in_transaction: self._fs_lock.release()

    def _validate_fid(self, fid: str):
        """
        Prevents Path Traversal attacks using canonical path resolution.
        Uses cached validation to avoid expensive OS calls during search loops.
        """
        return _cached_validate_fid(self.repo_path, fid)

    def update_decision(self, filename: str, updates: dict, commit_msg: str):
        filename = self._validate_fid(filename)
        self._enforce_trust()
        if not self._in_transaction: self._fs_lock.acquire(exclusive=True)
        try:
            if self._in_transaction and self._current_tx: self._current_tx.stage_file(filename)
            file_path = os.path.join(self.repo_path, filename)
            with open(file_path, "r", encoding="utf-8") as f: content = f.read()
            old_data, body = MemoryLoader.parse(content)

            import copy
            new_data = copy.deepcopy(old_data)
            CORE_FIELDS = ["status", "kind", "supersedes", "superseded_by", "merge_status", "enrichment_status", "timestamp", "fid", "source", "content"]
            
            # V7.0: Normalize procedural format before applying updates
            updates_normalized = updates.copy()
            if 'procedural' in updates_normalized and updates_normalized['procedural']:
                from ledgermind.core.core.schemas import ProceduralContent, ProceduralStep
                proc = updates_normalized['procedural']
                if isinstance(proc, list):
                    try:
                        steps = [
                            ProceduralStep(**step) if isinstance(step, dict) else step
                            for step in proc
                        ]
                        updates_normalized['procedural'] = ProceduralContent(steps=steps)
                    except Exception as proc_err:
                        logger.warning(f"Failed to normalize procedural: {proc_err}")
                        updates_normalized['procedural'] = None
            
            for field in CORE_FIELDS:
                if field in updates_normalized: new_data[field] = updates_normalized[field]

            new_data.pop("title", None)
            new_data.pop("target", None)
            if "context" not in new_data: new_data["context"] = {}
            clean_updates = {k: v for k, v in updates_normalized.items() if k not in CORE_FIELDS}
            new_data["context"].update(clean_updates)
            for field in CORE_FIELDS: new_data["context"].pop(field, None)
            
            TransitionValidator.validate_update(old_data, new_data)
            new_content = MemoryLoader.stringify(new_data, body)
            import hashlib
            h = hashlib.sha256()
            h.update(new_content.encode('utf-8'))
            content_hash = h.hexdigest()
            with open(file_path, "w", encoding="utf-8") as f: f.write(new_content)
            
            try:
                stat = os.stat(file_path)
                IntegrityChecker._file_data_cache[file_path] = (stat.st_mtime_ns, new_data)
                IntegrityChecker._state_cache.pop(self.repo_path, None)
            except OSError: pass

            ctx = new_data.get("context", {})
            ts = new_data.get("timestamp")
            if isinstance(ts, str): ts = datetime.fromisoformat(ts)
            final_target_upd = new_data.get("target") or ctx.get("target") or old_data.get("context", {}).get("target") or "unknown"
            final_ns_upd = ctx.get("namespace") or old_data.get("context", {}).get("namespace") or "default"
            
            if not ts:
                existing_meta = self.meta.get_by_fid(filename)
                if existing_meta:
                    ts = existing_meta.get('timestamp')
                    if isinstance(ts, str):
                        try: ts = datetime.fromisoformat(ts)
                        except ValueError: ts = None

            self._upsert_metadata(
                fid=filename, target=final_target_upd, namespace=final_ns_upd,
                kind=new_data.get("kind"), timestamp=ts or datetime.now(), content=new_data.get("content", ""),
                context=ctx, status=new_data.get("status") or ctx.get("status"),
                title=new_data.get("title"), content_hash=content_hash,
                supersedes=new_data.get("supersedes"), superseded_by=new_data.get("superseded_by"),
                merge_status=new_data.get("merge_status"), enrichment_status=new_data.get("enrichment_status")
            )
            if not self._in_transaction:
                IntegrityChecker.validate(self.repo_path, fid=filename, data=new_data, meta_store=self.meta)
                self.audit.update_artifact(filename, new_content, commit_msg)
            elif isinstance(self.audit, GitAuditProvider):
                self.audit.run(["add", "--", filename])
        except Exception as e:
            if not self._in_transaction:
                with open(file_path, "w", encoding="utf-8") as f: f.write(content)
            from .semantic_store.transitions import TransitionError
            from ledgermind.core.stores.semantic_store.integrity import IntegrityViolation
            if isinstance(e, (ConflictError, TransitionError, IntegrityViolation)): raise
            raise RuntimeError(f"Update Failed: {e}")
        finally:
            if not self._in_transaction: self._fs_lock.release()

    def list_decisions(self) -> List[str]:
        should_lock = not self._in_transaction
        if should_lock: self._fs_lock.acquire(exclusive=False)
        try: return [m['fid'] for m in self.meta.list_all()]
        finally: 
            if should_lock: self._fs_lock.release()

    def purge_memory(self, fid: str):
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
        """Return only 'active' records as conflicts. Draft records are not conflicts."""
        should_lock = not self._in_transaction
        if should_lock: self._fs_lock.acquire(exclusive=False)
        try:
            cursor = self.meta._conn.cursor()
            cursor.execute(
                "SELECT fid FROM semantic_meta WHERE target = ? AND namespace = ? AND status = 'active' AND kind IN ('decision', 'proposal')",
                (target, namespace)
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            if should_lock: self._fs_lock.release()
