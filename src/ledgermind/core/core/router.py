from typing import Optional, List, Any
from .schemas import MemoryEvent, MemoryDecision, ResolutionIntent, SEMANTIC_KINDS, KIND_DECISION
from ledgermind.core.reasoning.conflict import ConflictEngine
from ledgermind.core.reasoning.resolution import ResolutionEngine

class MemoryRouter:
    """
    Router that determines where a memory event should be stored and enforces conflict policies.
    """
    def __init__(self, 
                 conflict_engine: Optional[ConflictEngine] = None,
                 resolution_engine: Optional[ResolutionEngine] = None):
        """
        Initialize the router with optional reasoning engines.
        """
        self.conflict_engine = conflict_engine
        self.resolution_engine = resolution_engine

    def _get_context_field(self, event: MemoryEvent, field: str) -> Any:
        """
        Helper to extract a field from event context (handles both dict and pydantic).
        """
        if not event.context:
            return None
        if hasattr(event.context, field):
            return getattr(event.context, field)
        return event.context.get(field)

    def route(self, event: MemoryEvent, intent: Optional[ResolutionIntent] = None) -> MemoryDecision:
        """
        Routes the event and enforces the conflict resolution invariant.
        
        If a conflict is detected for a decision, it requires a valid ResolutionIntent.
        """

        if self.conflict_engine and event.kind == KIND_DECISION:
            conflicts = self.conflict_engine.get_conflict_files(event)
            if conflicts:
                target = self._get_context_field(event, "target")
                if not intent:
                    return MemoryDecision(
                        should_persist=False,
                        store_type="none",
                        reason=f"CONFLICT: Active decisions for target '{target}' exist: {conflicts}. ResolutionIntent required."
                    )
                
                if not self.resolution_engine or not self.resolution_engine.validate_intent(intent, conflicts):
                    return MemoryDecision(
                        should_persist=False,
                        store_type="none",
                        reason=f"CONFLICT: Provided ResolutionIntent is invalid or does not cover all conflicts: {conflicts}."
                    )

        if event.kind in SEMANTIC_KINDS or (intent and intent.resolution_type == "supersede"):
            store_type = "semantic"
        else:
            store_type = "episodic"
        
        return MemoryDecision(
            should_persist=True,
            store_type=store_type,
            reason=f"Accepted {event.kind} for {store_type} storage"
        )

