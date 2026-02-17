from typing import List, Optional, Any
import os
from agent_memory_core.core.schemas import MemoryEvent, KIND_DECISION
from agent_memory_core.stores.semantic_store.loader import MemoryLoader

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
        """
        if not event.context:
            return None
        # Handle both pydantic model and dict
        if hasattr(event.context, "target"):
            return event.context.target
        return event.context.get("target")

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

    def get_conflict_files(self, event: MemoryEvent) -> List[str]:
        """
        Identify files in the semantic store that conflict with the given event.
        
        A conflict occurs if an existing active decision has the same target.
        """
        if event.kind != KIND_DECISION:
            return []

        new_target = self._get_target(event)
        if not new_target:
            return []

        # Optimization: use metadata index if available
        if self.meta:
            ns = self._get_namespace(event)
            fid = self.meta.get_active_fid(new_target, namespace=ns)
            return [fid] if fid else []

        raise RuntimeError("Metadata store required for performance")

    def check_for_conflicts(self, event: MemoryEvent) -> Optional[str]:
        """
        Check for conflicts and return a human-readable message if any exist.
        """
        conflicts = self.get_conflict_files(event)
        if conflicts:
            return f"Conflict detected with: {', '.join(conflicts)}"
        return None