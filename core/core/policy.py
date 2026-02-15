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

        if event.kind == "result" and event.context.get("reused"):
            return True

        return False
