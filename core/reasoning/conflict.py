from typing import List, Optional
import os
from core.schemas import MemoryEvent, KIND_DECISION
from stores.semantic_store.loader import MemoryLoader

class ConflictEngine:
    """
    Engine for detecting conflicts between memory events and existing state.
    """
    def __init__(self, semantic_store_path: str):
        self.path = semantic_store_path

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

        conflicts = []
        try:
            files = [f for f in os.listdir(self.path) if f.endswith(".md") or f.endswith(".yaml")]
        except FileNotFoundError:
            return []
        
        for filename in files:
            try:
                with open(os.path.join(self.path, filename), 'r', encoding='utf-8') as f:
                    data, _ = MemoryLoader.parse(f.read())
                    
                ctx = data.get("context", {})
                if (data.get("kind") == KIND_DECISION and 
                    ctx.get("target") == new_target and 
                    ctx.get("status") == "active"):
                    conflicts.append(filename)
            except (IOError, ValueError, KeyError):
                # ValueError might be raised by MemoryLoader.parse if content is invalid
                continue
        return conflicts

    def check_for_conflicts(self, event: MemoryEvent) -> Optional[str]:
        """
        Check for conflicts and return a human-readable message if any exist.
        """
        conflicts = self.get_conflict_files(event)
        if conflicts:
            return f"Conflict detected with: {', '.join(conflicts)}"
        return None