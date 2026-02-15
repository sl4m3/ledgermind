import os
import yaml
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from core.router import MemoryRouter
from core.policy import MemoryPolicy
from core.schemas import (
    MemoryEvent, MemoryDecision, ResolutionIntent, TrustBoundary, 
    DecisionContent, SEMANTIC_KINDS, KIND_DECISION
)
from stores.episodic import EpisodicStore
from stores.semantic import SemanticStore
from reasoning.conflict import ConflictEngine
from reasoning.resolution import ResolutionEngine
from reasoning.decay import DecayEngine, DecayReport

class Memory:
    """
    The main entry point for the agent-memory-core.
    Provides methods for processing events, recording decisions, and managing knowledge decay.
    """
    def __init__(self, 
                 storage_path: str = "./memory", 
                 ttl_days: int = 30, 
                 trust_boundary: TrustBoundary = TrustBoundary.AGENT_WITH_INTENT,
                 episodic_store: Optional[EpisodicStore] = None,
                 semantic_store: Optional[SemanticStore] = None):
        """
        Initialize the memory system.
        
        :param storage_path: Base directory for all memory storage.
        :param ttl_days: Number of days before episodic memory starts to decay.
        :param trust_boundary: Security policy for determining what can be persisted.
        """
        self.storage_path = storage_path
        self.trust_boundary = trust_boundary
        
        try:
            if not os.path.exists(storage_path):
                os.makedirs(storage_path, exist_ok=True)
        except PermissionError:
            raise ValueError(f"No permission to create storage path: {storage_path}")
            
        self.policy = MemoryPolicy()
        
        self.episodic = episodic_store or EpisodicStore(os.path.join(storage_path, "episodic.db"))
        self.semantic = semantic_store or SemanticStore(os.path.join(storage_path, "semantic"), trust_boundary=trust_boundary)
        
        self.conflict_engine = ConflictEngine(self.semantic.repo_path)
        self.resolution_engine = ResolutionEngine(self.semantic.repo_path)
        self.decay_engine = DecayEngine(ttl_days=ttl_days)
        
        self.router = MemoryRouter(
            self.policy, 
            self.conflict_engine, 
            self.resolution_engine
        )

    def process_event(self, 
                      source: str, 
                      kind: str, 
                      content: str, 
                      context: Optional[Union[DecisionContent, Dict[str, Any]]] = None,
                      intent: Optional[ResolutionIntent] = None) -> MemoryDecision:
        """
        Process an incoming event and decide whether to persist it.
        """
        if (self.trust_boundary == TrustBoundary.HUMAN_ONLY and 
            source == "agent" and 
            kind == KIND_DECISION):
            return MemoryDecision(
                should_persist=False,
                store_type="none",
                reason="Trust Boundary Violation"
            )

        # Build and Validate event
        event = MemoryEvent(
            source=source,
            kind=kind,
            content=content,
            context=context or {}
        )
        
        decision = self.router.route(event, intent=intent)
        
        if decision.should_persist:
            if decision.store_type == "episodic":
                self.episodic.append(event)
            elif decision.store_type == "semantic":
                # Ensure bidirectional links in context before saving
                if intent and intent.resolution_type == "supersede" and isinstance(event.context, DecisionContent):
                    event.context.supersedes = intent.target_decision_ids
                
                new_fid = self.semantic.save(event)
                
                if intent and intent.resolution_type == "supersede":
                    for old_id in intent.target_decision_ids:
                        self.semantic.update_decision(
                            old_id, 
                            {"status": "superseded", "superseded_by": new_fid},
                            commit_msg=f"Superseded by {new_fid}"
                        )
                # Immortal Link
                self.episodic.append(event, linked_id=new_fid)
                
        return decision

    def get_decisions(self) -> List[str]:
        """
        List all active decision identifiers in the semantic store.
        """
        return self.semantic.list_decisions()

    def get_recent_events(self, limit: int = 10, include_archived: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve recent events from the episodic store.
        """
        status = None if include_archived else 'active'
        return self.episodic.query(limit=limit, status=status)

    def link_evidence(self, event_id: int, semantic_id: str):
        """
        Manually link an episodic event to a semantic record.
        """
        self.episodic.link_to_semantic(event_id, semantic_id)

    def run_decay(self, dry_run: bool = False) -> DecayReport:
        """
        Execute the decay process for episodic memories.
        """
        active_events = self.episodic.query(limit=10000, status='active')
        archived_events = self.episodic.query(limit=10000, status='archived')
        to_archive, to_prune, retained = self.decay_engine.evaluate(active_events + archived_events)
        
        if not dry_run:
            self.episodic.mark_archived(to_archive)
            self.episodic.physical_prune(to_prune)
            
        return DecayReport(len(to_archive), len(to_prune), retained)

    def record_decision(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> MemoryDecision:
        """
        Helper to record a new decision in semantic memory.
        """
        ctx = {
            "title": title,
            "target": target,
            "status": "active",
            "rationale": rationale,
            "consequences": consequences or []
        }
        return self.process_event(
            source="agent",
            kind=KIND_DECISION,
            content=title,
            context=ctx
        )

    def supersede_decision(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> MemoryDecision:
        """
        Helper to evolve knowledge by superseding existing decisions.
        """
        active_files = self.semantic.list_active_conflicts(target)
        for oid in old_decision_ids:
            if oid not in active_files:
                raise ValueError(f"Cannot supersede {oid}: it is not an active decision for target {target}")

        intent = ResolutionIntent(
            resolution_type="supersede",
            rationale=rationale,
            target_decision_ids=old_decision_ids
        )
        ctx = {
            "title": title,
            "target": target,
            "status": "active",
            "rationale": rationale,
            "consequences": consequences or []
        }
        return self.process_event(
            source="agent",
            kind=KIND_DECISION,
            content=title,
            context=ctx,
            intent=intent
        )

