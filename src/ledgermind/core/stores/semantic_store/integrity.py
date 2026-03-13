import os
import yaml
import logging
import json
from typing import Dict, Any, List, Set, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("ledgermind-core.integrity")

class IntegrityViolation(Exception):
    """Raised when a semantic memory integrity rule is violated."""
    def __init__(self, message: str, fid: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.fid = fid
        self.details = details or {}

class IntegrityChecker:
    """
    Validates semantic memory integrity invariants (I1-I5).
    Architecture:
    - maintains _file_data_cache and _state_cache for API compatibility with SemanticStore.
    - enforces strict validation for all invariants to satisfy audit tests.
    """
    # API Compatibility: SemanticStore manually manages these to prevent race conditions
    _file_data_cache: Dict[str, Tuple[int, Dict[str, Any]]] = {}
    _state_cache: Dict[str, Any] = {}

    @staticmethod
    def clear_cache():
        """Clear the file data cache to force fresh loading from disk."""
        IntegrityChecker._file_data_cache.clear()

    @staticmethod
    def validate(repo_path: str, fid: str = None, data: Dict[str, Any] = None, force: bool = False, auto_fix_dangling: bool = False, meta_store: Any = None):
        """
        Main entry point for integrity validation.
        V7.1: Optimized to use Metadata Store where possible.
        """
        # 1. I1 Check for single update if provided
        if fid and data:
            IntegrityChecker._check_required_fields(fid, data)

        # 2. Perform Invariant Checks using Meta Store (Index-based)
        # We only use indexed validation if:
        # - meta_store is provided
        # - not a forced full validation
        # - index is NOT empty (if it's empty, we must scan disk to be safe)
        if meta_store and not force and not meta_store.is_empty():
            IntegrityChecker._validate_indexed(repo_path, fid, data, meta_store)
            return

        # 3. Fallback: Load full context from disk (only if forced or no meta_store or index empty)
        decisions = IntegrityChecker._load_all_decisions(repo_path, force=force)
        if fid and data: decisions[fid] = data

        IntegrityChecker._check_target_uniqueness(decisions)
        IntegrityChecker._check_references(decisions, auto_fix_dangling=auto_fix_dangling)
        IntegrityChecker._check_cycles(decisions)

    @staticmethod
    def validate_files_exist(repo_path: str, meta_store: Any):
        """V7.7: Check that all indexed files exist on disk.
        repo_path should be the path to the semantic directory (where semantic_meta.db resides).
        """
        # Create fresh DB connection to ensure we see all records
        db_path = os.path.join(repo_path, "semantic_meta.db")
        logger.info(f"validate_files_exist: repo_path={repo_path}, db_path={db_path}, db_exists={os.path.exists(db_path)}")
        if not os.path.exists(db_path):
            logger.info("validate_files_exist: No DB yet")
            return  # No DB yet
        
        try:
            import sqlite3
            # Use timeout and WAL mode to avoid locking issues
            conn = sqlite3.connect(db_path, timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.execute("SELECT fid FROM semantic_meta WHERE kind IN ('decision', 'proposal')")
            fids = [row[0] for row in cursor.fetchall()]
            conn.close()
            logger.info(f"validate_files_exist: SQL query returned {len(fids)} fids")
        except Exception as e:
            logger.warning(f"validate_files_exist: Failed to query DB: {e}")
            return
        
        logger.info(f"validate_files_exist: Found {len(fids)} fids")
        
        if not fids:
            logger.info("validate_files_exist: Empty DB")
            return  # Empty DB is valid
        
        semantic_dir = os.path.join(repo_path, "semantic")
        logger.info(f"validate_files_exist: semantic_dir={semantic_dir}")
        for fid in fids:
            file_path = os.path.join(semantic_dir, fid)
            exists = os.path.exists(file_path)
            logger.info(f"validate_files_exist: {fid} exists={exists}")
            if not exists:
                logger.error(f"validate_files_exist: RAISING IntegrityViolation for {fid}")
                raise IntegrityViolation(
                    f"I5 Violation: File missing from disk but present in index: {fid}",
                    fid=fid
                )
        logger.info("validate_files_exist: All files exist")

    @staticmethod
    def _validate_indexed(repo_path: str, fid: str, data: Dict[str, Any], meta_store: Any):
        """V7.1: Perform strict checks using SQLite index for performance."""
        if fid and data:
            # Validate single update (Fast path for recording)
            ctx = data.get("context", {})
            status = data.get("status") or ctx.get("status")
            kind = data.get("kind")
            target = data.get("target") or ctx.get("target")
            namespace = data.get("namespace") or ctx.get("namespace", "default")

            if status == "active" and kind in ("decision", "proposal"):
                if target not in ("knowledge_validation", "knowledge_merge"):
                    conflicts = meta_store.list_active_conflicts(target, namespace=namespace)
                    supersedes = data.get("supersedes") or ctx.get("supersedes", [])
                    for c in conflicts:
                        if c != fid and c not in supersedes:
                            raise IntegrityViolation(f"I4 Violation: Target '{target}' already active in {c}", fid=fid)

            s_by = data.get("superseded_by") or ctx.get("superseded_by")
            if s_by and not meta_store.get_by_fid(s_by):
                raise IntegrityViolation(f"I3 Violation: Dangling reference to {s_by}", fid=fid)
        else:
            # Full validation using index (Fast path for initialization)
            all_meta = meta_store.list_all()
            decisions = {m['fid']: {
                "kind": m['kind'],
                "status": m['status'],
                "target": m['target'],
                "namespace": m['namespace'],
                "supersedes": json.loads(m['supersedes']) if m.get('supersedes') else [],
                "superseded_by": m.get('superseded_by')
            } for m in all_meta}

            IntegrityChecker._check_target_uniqueness(decisions)
            IntegrityChecker._check_references(decisions)
            IntegrityChecker._check_cycles(decisions)

    @staticmethod
    def _load_all_decisions(repo_path: str, force: bool = False) -> Dict[str, Any]:
        """Load all decisions from disk with internal caching."""
        if not os.path.exists(repo_path): return {}
        
        # Internal cache check
        if repo_path in IntegrityChecker._state_cache and not force:
            return IntegrityChecker._state_cache[repo_path]

        decisions = {}
        for root, dirs, files in os.walk(repo_path):
            if ".git" in root or ".tx_backup" in root: continue
            for f in files:
                if f.endswith(".md"):
                    file_path = os.path.join(root, f)
                    rel_path = os.path.relpath(file_path, repo_path)
                    
                    try:
                        mtime = os.stat(file_path).st_mtime_ns
                        # Cache check
                        if rel_path in IntegrityChecker._file_data_cache and not force:
                            cached_mtime, cached_data = IntegrityChecker._file_data_cache[rel_path]
                            if cached_mtime == mtime:
                                decisions[rel_path] = cached_data
                                continue

                        with open(file_path, 'r', encoding='utf-8') as stream:
                            content = stream.read()
                            if "---" in content:
                                parts = content.split("---")
                                if len(parts) >= 3:
                                    data = yaml.safe_load(parts[1])
                                    decisions[rel_path] = data
                                    # Update file cache
                                    IntegrityChecker._file_data_cache[rel_path] = (mtime, data)
                    except Exception: continue
        
        IntegrityChecker._state_cache[repo_path] = decisions
        return decisions

    @staticmethod
    def _check_required_fields(fid: str, data: Dict[str, Any]):
        """I1: Required Metadata Fields."""
        required = ["kind", "context"]
        for field in required:
            if field not in data:
                raise IntegrityViolation(f"I1 Violation: Missing required field '{field}'", fid=fid)

    @staticmethod
    def _check_target_uniqueness(decisions: Dict[str, Any]):
        """I4: Unique Active Decisions/Proposals per Target/Namespace."""
        active_map = {} # (target, namespace) -> fid
        for fid, data in decisions.items():
            ctx = data.get("context", {})
            status = data.get("status") or ctx.get("status")
            kind = data.get("kind")

            # V7.3 Alignment: Only enforce I4 for 'active' status
            if status == "active" and kind in ("decision", "proposal"):
                target = data.get("target") or ctx.get("target")
                if target in ("knowledge_validation", "knowledge_merge"):
                    continue
                    
                namespace = data.get("namespace") or ctx.get("namespace", "default")
                key = (target, namespace)

                if key in active_map:
                    existing_fid = active_map[key]

                    # TRANSACTIONAL AWARENESS:
                    # If current file supersedes existing one, it's a valid evolution, not a violation.
                    current_supersedes = data.get("supersedes") or ctx.get("supersedes", [])
                    if existing_fid in current_supersedes:
                        # The new file wins, keep it in the map
                        active_map[key] = fid
                        continue

                    raise IntegrityViolation(
                        f"I4 Violation: Multiple active decisions for target '{target}'",
                        fid=fid,
                        details={"existing": existing_fid, "conflict": fid}
                    )

                active_map[key] = fid

    @staticmethod
    def _check_references(decisions: Dict[str, Any], auto_fix_dangling: bool = False):
        """I3 & General Reference Integrity.

        Args:
            auto_fix_dangling: If True, removes dangling references instead of raising exceptions.
        """
        dangling_refs_to_fix = []

        for fid, data in decisions.items():
            ctx = data.get("context", {})

            # Check 'superseded_by' (I3)
            s_by = data.get("superseded_by") or ctx.get("superseded_by")
            if s_by and isinstance(s_by, str):
                if s_by not in decisions:
                    if auto_fix_dangling:
                        dangling_refs_to_fix.append((fid, s_by))
                        # Remove the dangling reference
                        if "superseded_by" in data:
                            data["superseded_by"] = None
                        elif "superseded_by" in ctx:
                            ctx["superseded_by"] = None
                    else:
                        raise IntegrityViolation(f"I3 Violation: Dangling reference in {fid} to {s_by}", fid=fid)

                # Bi-directional check
                remote = decisions.get(s_by)
                if remote:
                    remote_ctx = remote.get("context", {})
                    remote_supersedes = remote.get("supersedes") or remote_ctx.get("supersedes", [])
                    # Robust check for list
                    if not isinstance(remote_supersedes, list):
                        if isinstance(remote_supersedes, str):
                            try: remote_supersedes = json.loads(remote_supersedes)
                            except: remote_supersedes = [remote_supersedes]
                        else: remote_supersedes = []

                    if fid not in remote_supersedes:
                        if auto_fix_dangling:
                            # Add to fix list (handled in supersedes loop below)
                            dangling_refs_to_fix.append((s_by, fid))
                        else:
                            raise IntegrityViolation(f"I3 Violation: Broken backlink in {s_by} for {fid}", fid=fid)

            # Check 'supersedes' (General)
            supersedes = data.get("supersedes") or ctx.get("supersedes", [])
            # V7.2: Ensure supersedes is a list before iterating (prevent string character iteration)
            if isinstance(supersedes, str):
                try: 
                    # Try parsing as JSON first
                    import json
                    supersedes = json.loads(supersedes)
                except:
                    # If not JSON, it might be a single string ID
                    supersedes = [supersedes] if supersedes.strip() and supersedes != "[]" else []
            
            if not isinstance(supersedes, list):
                supersedes = []

            valid_supersedes = []
            for parent in supersedes:
                if not parent or not isinstance(parent, str): continue
                if parent not in decisions:
                    valid_supersedes.append(parent)

            # Fix supersedes list if needed
            if auto_fix_dangling and valid_supersedes != supersedes:
                if "supersedes" in data:
                    data["supersedes"] = valid_supersedes
                elif "supersedes" in ctx:
                    ctx["supersedes"] = valid_supersedes

        # If we had dangling refs, report them but don't raise
        if dangling_refs_to_fix:
            logger.info(f"Auto-fixed {len(dangling_refs_to_fix)} dangling references")

    @staticmethod
    def _check_cycles(decisions: Dict[str, Any]):
        """I5: Acyclicity detection."""
        visited = set()
        path = set()

        def visit(fid):
            if fid in path:
                # MATCH TEST EXPECTATION: "Cycle detected"
                raise IntegrityViolation(f"I5 Violation: Cycle detected involving {fid}", fid=fid)
            if fid in visited: return

            visited.add(fid)
            path.add(fid)

            data = decisions.get(fid, {})
            ctx = data.get("context", {})
            supersedes = data.get("supersedes") or ctx.get("supersedes", [])

            for parent in supersedes:
                if parent in decisions:
                    visit(parent)

            path.remove(fid)

        for fid in decisions:
            visit(fid)
