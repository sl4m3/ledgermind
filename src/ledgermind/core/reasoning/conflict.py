from typing import List, Optional, Any
import os
from ledgermind.core.core.schemas import MemoryEvent, KIND_DECISION, KIND_INTERVENTION, ResolutionIntent
from ledgermind.core.stores.semantic_store.loader import MemoryLoader

class ConflictEngine:
    """
    Engine for detecting conflicts and analyzing resolution intents.
    """
    def __init__(self, semantic_store_path: str, meta_store: Optional[Any] = None):
        self.path = semantic_store_path
        self.meta = meta_store

    def analyze_intent(self, event: MemoryEvent) -> Optional[ResolutionIntent]:
        """
        Analyzes the event to determine if it should supersede existing knowledge.
        """
        # Decisions and Interventions trigger intent analysis
        if event.kind not in (KIND_DECISION, KIND_INTERVENTION):
            return ResolutionIntent(resolution_type="record", rationale="Standard log")

        target = self._get_target(event)
        if not target:
            return ResolutionIntent(resolution_type="record", rationale="No target identified")

        # Find existing active decisions for the same target
        conflicts = self.get_conflict_files(event)
        if conflicts:
            return ResolutionIntent(
                resolution_type="supersede",
                rationale=f"New information for target '{target}' supersedes existing state.",
                target_decision_ids=conflicts
            )

        return ResolutionIntent(resolution_type="record", rationale="First entry for target")

    def _get_target(self, event: MemoryEvent) -> Optional[str]:
        if not event.context: return None
        target = None
        if hasattr(event.context, "target"):
            target = event.context.target
        elif isinstance(event.context, dict):
            target = event.context.get("target")
        return target

    def _get_namespace(self, event: MemoryEvent) -> str:
        if not event.context: return "default"
        if hasattr(event.context, "namespace"):
            return getattr(event.context, "namespace") or "default"
        if isinstance(event.context, dict):
            return event.context.get("namespace", "default")
        return "default"

    def get_conflict_files(self, event: MemoryEvent, namespace: Optional[str] = None) -> List[str]:
        new_target = self._get_target(event)
        if not new_target: return []

        if self.meta:
            ns = namespace or self._get_namespace(event)
            # Find all active decisions for the same target using standard list_all
            metas = self.meta.list_all(target=new_target, namespace=ns)
            fids = [m['fid'] for m in metas if m.get('status') == 'active']
            return fids

        return []

    def check_for_conflicts(self, event: MemoryEvent, namespace: Optional[str] = None, supersedes: Optional[List[str]] = None) -> Optional[str]:
        # Only check conflicts for decisions and interventions
        if event.kind not in (KIND_DECISION, KIND_INTERVENTION):
            return None

        conflicts = self.get_conflict_files(event, namespace=namespace)
        if conflicts:
            if supersedes:
                conflicts = [c for c in conflicts if c not in supersedes]
            if conflicts:
                return f"Conflict detected with: {', '.join(conflicts)}"
        return None
