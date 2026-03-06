from typing import List, Optional, Any
import os
from ledgermind.core.core.schemas import MemoryEvent, KIND_DECISION
from ledgermind.core.stores.semantic_store.loader import MemoryLoader

class ConflictEngine:
    """
    Engine for detecting conflicts between memory events and existing state.
    """
    def __init__(self, semantic_store_path: str, meta_store: Optional[Any] = None):
        self.path = semantic_store_path
        self.meta = meta_store

    def _get_target(self, event: MemoryEvent) -> Optional[str]:
        """
        Extract the target identifier from a memory event.
        Hierarchy is normalized to the first level (e.g., 'ledgermind/server' -> 'ledgermind').
        """
        if not event.context:
            return None
        # Handle both pydantic model and dict
        target = None
        if hasattr(event.context, "target"):
            target = event.context.target
        elif isinstance(event.context, dict):
            target = event.context.get("target")
            
        if target:
            # We now support granular knowledge. No more forced prefix-based conflicts.
            # A conflict only exists for the EXACT SAME target path.
            return target
        return target

    def _get_namespace(self, event: MemoryEvent) -> str:
        if not event.context:
            return "default"
        # Handle both pydantic model and dict
        if hasattr(event.context, "namespace"):
            val = getattr(event.context, "namespace")
            return val or "default"
        if isinstance(event.context, dict):
            return event.context.get("namespace", "default")
        return "default"

    def get_conflict_files(self, event: MemoryEvent, namespace: Optional[str] = None) -> List[str]:
        """
        Identify files in the semantic store that conflict with the given event.
        
        A conflict occurs if an existing active decision has the exact same target.
        """
        if event.kind != KIND_DECISION:
            return []

        new_target = self._get_target(event)
        if not new_target:
            return []

        # Optimization: use metadata index if available
        if self.meta:
            ns = namespace or self._get_namespace(event)
            
            # Find all active decisions where the target matches the base level
            # e.g., if new_target is 'ledgermind', find 'ledgermind/server', 'ledgermind/storage', etc.
            fids = self.meta.get_active_fids_by_base_target(new_target, namespace=ns)
            return fids

        raise RuntimeError("Metadata store required for performance")

    def check_for_conflicts(self, event: MemoryEvent, namespace: Optional[str] = None, supersedes: Optional[List[str]] = None) -> Optional[str]:
        """
        Check for conflicts and return a human-readable message if any exist.
        Excludes files that are intended to be superseded by this event.
        """
        conflicts = self.get_conflict_files(event, namespace=namespace)
        if conflicts:
            # Filter out files we are already superseding in this transaction
            if supersedes:
                conflicts = [c for c in conflicts if c not in supersedes]
            
            if conflicts:
                return f"Conflict detected with: {', '.join(conflicts)}"
        return None