from .schemas import MemoryEvent

class MemoryPolicy:
    def should_persist(self, event: MemoryEvent) -> bool:
        """
        Deterministic logic to decide if an event should be persisted.
        """
        if event.kind in ["decision", "constraint"]:
            return True
        
        if event.kind == "config_change":
            return True

        if event.kind == "context_snapshot":
            return True

        if event.kind == "commit_change":
            return True

        if event.kind == "result":
            return True

        return False
