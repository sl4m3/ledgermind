from typing import List, Dict, Any, Set
import os
import yaml
import logging

logger = logging.getLogger("ledgermind-core.integrity")

class IntegrityViolation(Exception):
    """
    Exception raised when a memory integrity invariant is violated.
    """
    def __init__(self, message: str, fid: str = None, details: Dict[str, Any] = None):
        if fid:
            message = f"[{fid}] {message}"
        super().__init__(message)
        self.fid = fid
        self.details = details or {}

class IntegrityChecker:
    """
    Validator for maintaining architectural invariants across the semantic store.
    """
    _state_cache: Dict[str, int] = {} # repo_path -> state_hash
    _file_data_cache: Dict[str, Any] = {} # full_path -> (mtime, data)

    @staticmethod
    def _get_state_hash(repo_path: str) -> int:
        """
        Generates a hash of the current repository state based on filenames and mtimes (ns).
        """
        all_files = []
        for root, _, filenames in os.walk(repo_path):
            if ".git" in root or ".tx_backup" in root: continue
            for f in filenames:
                if f.endswith(".md") or f.endswith(".yaml"):
                    rel_path = os.path.relpath(os.path.join(root, f), repo_path)
                    all_files.append(rel_path)
        
        files = sorted(all_files)
        state = []
        for f in files:
            try:
                stat = os.stat(os.path.join(repo_path, f))
                state.append((f, stat.st_mtime_ns))
            except OSError:
                continue
        return hash(tuple(state))

    @staticmethod
    def validate(repo_path: str, force: bool = False, fid: str = None):
        """
        Scans the repository and ensures all integrity invariants are met.
        Supports incremental validation if fid is provided.
        """
        if not fid:
            current_hash = IntegrityChecker._get_state_hash(repo_path)
            if not force and IntegrityChecker._state_cache.get(repo_path) == current_hash:
                return
        
        # Incremental logic: if fid provided, we skip the global walk for hash
        # but we still need to build the 'decisions' map for the subset being checked

        # Clear data cache if forced
        if force:
            IntegrityChecker._file_data_cache = {k: v for k, v in IntegrityChecker._file_data_cache.items() if not k.startswith(repo_path)}

        all_files = []
        if fid:
            # Incremental validation: only check this file and its direct links
            # We still need the list of all files to verify presence of link targets
            # But we can get this from os.listdir or similar if we want to be super fast.
            # For now, let's just use the cached walk if available or do a quick list.
            all_files = [fid]
        else:
            for root, _, filenames in os.walk(repo_path):
                if ".git" in root or ".tx_backup" in root: continue
                for f in filenames:
                    if f.endswith(".md") or f.endswith(".yaml"):
                        rel_path = os.path.relpath(os.path.join(root, f), repo_path)
                        all_files.append(rel_path)
        
        decisions = {}
        from .loader import MemoryLoader

        # If incremental, we only parse the files we care about,
        # but we need 'decisions' map of ALL files to verify links.
        # This is where we MUST rely on cache for the rest of the repo.
        if fid:
            # For incremental check to work, we need a full 'decisions' view.
            # If cache is empty, we have to do a full scan anyway once.
            if not IntegrityChecker._file_data_cache:
                IntegrityChecker.validate(repo_path, force=True)
                return # Full check was done
            
            # Use cached decisions for everything else
            for f_path, (ts, data) in IntegrityChecker._file_data_cache.items():
                rel = os.path.relpath(f_path, repo_path)
                decisions[rel] = data
        
        for f in all_files:
            file_path = os.path.join(repo_path, f)
            try:
                stat = os.stat(file_path)
                mtime_ns = stat.st_mtime_ns
                cached_mtime_ns, cached_data = IntegrityChecker._file_data_cache.get(file_path, (0, None))
                
                if cached_data and cached_mtime_ns == mtime_ns:
                    data = cached_data
                else:
                    with open(file_path, 'r', encoding='utf-8') as stream:
                        content = stream.read()
                        data, _ = MemoryLoader.parse(content)
                        if not data:
                            logger.error(f"Integrity check failed for {f}. Content length: {len(content)}")
                            logger.error(f"CONTENT START: {content[:200]}")
                            raise IntegrityViolation(f"Corrupted or empty frontmatter", fid=f)
                        IntegrityChecker._file_data_cache[file_path] = (mtime_ns, data)
                
                decisions[f] = data
            except (OSError, IntegrityViolation) as e:
                if isinstance(e, IntegrityViolation): raise
                continue

        # I4: Single active decision per target per namespace
        active_targets: Dict[tuple, str] = {}
        
        for fid, data in decisions.items():
            if not data or "context" not in data:
                continue
                
            kind = data.get("kind", "decision") # Default to decision for legacy
            ctx = data["context"]
            target = ctx.get("target")
            status = ctx.get("status")
            
            # Determine namespace from directory structure if not explicitly in context
            rel_dir = os.path.dirname(fid)
            namespace = ctx.get("namespace") or (rel_dir if rel_dir else "default")

            # I4: Single active decision per target
            # ONLY for decisions, proposals are excluded from reality checks
            if kind == "decision" and status == "active" and target:
                key = (target, namespace)
                if key in active_targets:
                    raise IntegrityViolation(
                        f"I4 Violation: Multiple active decisions for target '{target}' in namespace '{namespace}'",
                        fid=fid,
                        details={"conflicting_file": active_targets[key]}
                    )
                active_targets[key] = fid

            # I3: Bidirectional Supersede
            superseded_by = ctx.get("superseded_by")
            if superseded_by:
                if superseded_by not in decisions:
                    raise IntegrityViolation(
                        f"I3 Violation: Dangling reference. Superseded by non-existent file.",
                        fid=fid,
                        details={"target": superseded_by}
                    )
                
                # Check remote backlink
                remote_ctx = decisions[superseded_by].get("context", {})
                if fid not in remote_ctx.get("supersedes", []):
                    raise IntegrityViolation(
                        f"I3 Violation: Broken backlink. {superseded_by} does not acknowledge via 'supersedes'.",
                        fid=fid,
                        details={"target": superseded_by}
                    )
                    
            # Check if all 'supersedes' point to existing files
            for old_fid in ctx.get("supersedes", []):
                if old_fid not in decisions:
                    raise IntegrityViolation(
                        f"Reference Violation: Claims to supersede non-existent file.",
                        fid=fid,
                        details={"target": old_fid}
                    )

        # I5: Acyclicity
        IntegrityChecker._check_cycles(decisions)
        
        # Update cache on success
        IntegrityChecker._state_cache[repo_path] = current_hash

    @staticmethod
    def _check_cycles(decisions: Dict[str, Any]):
        visited: Set[str] = set()
        stack: Set[str] = set()

        def visit(fid):
            if fid in stack:
                raise IntegrityViolation(f"I5 Violation: Cycle detected in knowledge evolution.", fid=fid)
            if fid in visited:
                return
            
            stack.add(fid)
            ctx = decisions.get(fid, {}).get("context", {})
            superseded_by = ctx.get("superseded_by")
            if superseded_by:
                visit(superseded_by)
            
            stack.remove(fid)
            visited.add(fid)

        for fid in decisions:
            if fid not in visited:
                visit(fid)
