import logging
import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from ..base_service import MemoryService
from ledgermind.core.core.schemas import (
    MemoryEvent, MemoryDecision, ResolutionIntent, TrustBoundary, 
    DecisionContent, DecisionStream, KIND_DECISION, KIND_PROPOSAL, KIND_INTERVENTION
)
from ledgermind.core.core.exceptions import ConflictError

logger = logging.getLogger("ledgermind.core.api.services.event_processing")

class EventProcessingService(MemoryService):
    """
    Service responsible for processing incoming events, 
    validation, conflict detection, and persistence.
    """
    
    @property
    def router(self):
        return self.context.router if hasattr(self.context, 'router') else None
        
    @property
    def conflict_engine(self):
        return self.context.conflict_engine

    def process_event(self, 
                      source: str, 
                      kind: str, 
                      content: str, 
                      context: Optional[Union[DecisionContent, DecisionStream, Dict[str, Any]]] = None,
                      intent: Optional[ResolutionIntent] = None,
                      namespace: Optional[str] = None,
                      vector: Optional[Any] = None,
                      timestamp: Optional[Union[datetime, str]] = None,
                      event_emitter: Any = None) -> MemoryDecision:
        """Core event processing logic."""
        effective_namespace = namespace or self.context.namespace
        final_timestamp = self._normalize_timestamp(timestamp)

        if (self.context.trust_boundary == TrustBoundary.HUMAN_ONLY and source == "agent" and kind == KIND_DECISION):
            return MemoryDecision(should_persist=False, store_type="none", reason="Trust Boundary Violation")

        if kind == KIND_INTERVENTION:
            context = self._handle_intervention(content, context, namespace)

        if isinstance(context, dict) and "decision_id" not in context:
            context["decision_id"] = str(uuid.uuid4())

        if kind == KIND_PROPOSAL:
            self._force_draft_status(context)

        event = MemoryEvent(source=source, kind=kind, content=content, context=context or {}, timestamp=final_timestamp)
        
        if self.episodic.find_duplicate(event, ignore_links=True).value:
            return MemoryDecision(should_persist=False, store_type="none", reason="Duplicate event detected")

        # Decision routing and conflict check
        # Use shared router from context (initialized by Memory)
        decision = self.context.router.route(event, intent=intent)
        if decision and decision.should_persist and decision.store_type == "semantic" and not intent:
             if conflict_msg := self.conflict_engine.check_for_conflicts(event, namespace=effective_namespace):
                 return MemoryDecision(should_persist=False, store_type="none", reason=f"Invariant Violation: {conflict_msg}")
        
        if decision and decision.should_persist:
            if decision.store_type == "episodic":
                if source in {"user", "agent"}:
                    ev_id = self.episodic.append(event).value
                    decision.metadata["event_id"] = ev_id
                    if event_emitter: event_emitter.emit("episodic_added", {"id": ev_id, "kind": event.kind})
            elif decision.store_type == "semantic":
                self._persist_semantic(event, decision, intent, effective_namespace, vector, source, event_emitter)

        return decision

    def _normalize_timestamp(self, timestamp: Any) -> datetime:
        if not timestamp: return datetime.now().replace(microsecond=(datetime.now().microsecond // 1000) * 1000)
        if isinstance(timestamp, str):
            try: return datetime.fromisoformat(timestamp.replace('Z', '+00:00')).replace(microsecond=0)
            except Exception: return datetime.now().replace(microsecond=0)
        return timestamp.replace(microsecond=(timestamp.microsecond // 1000) * 1000)

    def _handle_intervention(self, content: str, context: Any, namespace: str) -> DecisionStream:
        stream = DecisionStream(
            decision_id=context.get('decision_id', str(uuid.uuid4())) if isinstance(context, dict) else getattr(context, 'decision_id', str(uuid.uuid4())),
            target=context.get('target', 'unknown') if isinstance(context, dict) else getattr(context, 'target', 'unknown'),
            title=context.get('title', content) if isinstance(context, dict) else getattr(context, 'title', content),
            rationale=context.get('rationale', content) if isinstance(context, dict) else getattr(context, 'rationale', content),
            namespace=namespace or self.context.namespace
        )
        return self.context.reflection_engine.lifecycle.process_intervention(stream, datetime.now())

    def _force_draft_status(self, context: Any):
        if isinstance(context, dict): context["status"] = "draft"
        elif hasattr(context, "status"): context.status = "draft"

    def _persist_semantic(self, event, decision, intent, namespace, vector, source, event_emitter):
        with self.transaction(description="Persist Semantic Record"):
            if intent and intent.resolution_type == "supersede":
                for old_id in intent.target_decision_ids:
                    old_meta = self.semantic.meta.get_by_fid(old_id)
                    if old_meta and old_meta.get('status') in ('active', 'pending_merge', 'accepted', 'draft'):
                        self.semantic.update_decision(old_id, {"status": "superseded"}, commit_msg="Deactivating for transition")

            to_supersede_ids = intent.target_decision_ids if (intent and intent.resolution_type == "supersede") else None
            if conflict_msg := self.conflict_engine.check_for_conflicts(event, namespace=namespace, supersedes=to_supersede_ids):
                raise ConflictError(f"Conflict detected: {conflict_msg}")

            # Prepare Context
            if isinstance(event.context, (DecisionContent, DecisionStream)):
                if intent and intent.resolution_type == "supersede": event.context.supersedes = intent.target_decision_ids
                event.context.namespace = namespace
                event.context = event.context.model_dump(mode='json')
            elif isinstance(event.context, dict):
                if intent and intent.resolution_type == "supersede": event.context["supersedes"] = intent.target_decision_ids
                event.context["namespace"] = namespace

            new_fid = self.semantic.save(event, namespace=namespace)
            
            # FORWARDING LOGIC: If the intent target is superseded, find the active proposal
            if intent and intent.resolution_type == "supersede" and intent.target_decision_ids:
                # This is standard superseding during recording
                for old_id in intent.target_decision_ids:
                    self.semantic.update_decision(old_id, {"status": "superseded", "superseded_by": new_fid}, commit_msg=f"Superseded by {new_fid}")
            
            # Resolve truth for linked_id if not a new record creation
            # (Handled below during episodic append)

            decision.metadata["file_id"] = new_fid
            if event_emitter: event_emitter.emit("semantic_added", {"id": new_fid, "kind": event.kind, "namespace": namespace})

            # Evidence Inheritance... (rest of method)
            grounding_ids = set()
            if isinstance(event.context, dict): grounding_ids.update(event.context.get('evidence_event_ids', []))
            
            # ...
            
        # ...
        
        INTERNAL_SOURCES = {"system", "reflection_engine", "bridge"}
        is_merge = event.kind == KIND_DECISION and ((isinstance(event.context, dict) and event.context.get('target') == "knowledge_merge") or (intent and intent.resolution_type == "supersede"))
        
        if source in {"user", "agent"} and not (source == "agent" and is_merge) and source not in INTERNAL_SOURCES:
            # RESOLVE LINKED ID: Ensure events go to the active truth (Merge Proposal or confirmed decision)
            linked_fid = new_fid
            if linked_fid:
                truth = self.context.memory._resolve_to_truth(linked_fid, mode="balanced")
                if truth and truth.get('fid') != linked_fid:
                    logger.info(f"Forwarding event from {linked_fid} to active truth {truth.get('fid')}")
                    linked_fid = truth.get('fid')

            ev_id = self.episodic.append(event, linked_id=linked_fid).value
            decision.metadata["event_id"] = ev_id
