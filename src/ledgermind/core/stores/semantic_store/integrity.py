from typing import List, Dict, Any, Set
import os
import yaml

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
        Generates a hash of the current repository state based on filenames and mtimes.
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
                mtime = os.path.getmtime(os.path.join(repo_path, f))
                state.append((f, mtime))
            except OSError:
                continue
        return hash(tuple(state))

    @staticmethod
    def validate(repo_path: str, force: bool = False):
        """
        Scans the repository and ensures all integrity invariants are met.
        
        Specifically checks:
        - I4: Single active decision per target.
        - I3: Bidirectional supersede links.
        - I5: Acyclic evolution graph.
        
        Raises IntegrityViolation if any invariant is broken.
        """
        current_hash = IntegrityChecker._get_state_hash(repo_path)
        if not force and IntegrityChecker._state_cache.get(repo_path) == current_hash:
            return

        all_files = []
        for root, _, filenames in os.walk(repo_path):
            if ".git" in root or ".tx_backup" in root: continue
            for f in filenames:
                if f.endswith(".md") or f.endswith(".yaml"):
                    rel_path = os.path.relpath(os.path.join(root, f), repo_path)
                    all_files.append(rel_path)
        
        decisions = {}
        
        from .loader import MemoryLoader
        
        for f in all_files:
            file_path = os.path.join(repo_path, f)
            try:
                mtime = os.path.getmtime(file_path)
                cached_mtime, cached_data = IntegrityChecker._file_data_cache.get(file_path, (0, None))
                
                if cached_data and cached_mtime == mtime:
                    data = cached_data
                else:
                    with open(file_path, 'r', encoding='utf-8') as stream:
                        content = stream.read()
                        data, _ = MemoryLoader.parse(content)
                        if not data:
                            raise IntegrityViolation(f"Corrupted or empty frontmatter", fid=f)
                        IntegrityChecker._file_data_cache[file_path] = (mtime, data)
                
                decisions[f] = data
            except (OSError, IntegrityViolation) as e:
                if isinstance(e, IntegrityViolation): raise
                continue

        # I4: Single active decision per target
        active_targets: Dict[str, str] = {}
        
        for fid, data in decisions.items():
            if not data or "context" not in data:
                continue
                
            kind = data.get("kind", "decision") # Default to decision for legacy
            ctx = data["context"]
            target = ctx.get("target")
            status = ctx.get("status")

            # I4: Single active decision per target
            # ONLY for decisions, proposals are excluded from reality checks
            if kind == "decision" and status == "active" and target:
                if target in active_targets:
                    raise IntegrityViolation(
                        f"I4 Violation: Multiple active decisions for target '{target}'",
                        fid=fid,
                        details={"conflicting_file": active_targets[target]}
                    )
                active_targets[target] = fid

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
