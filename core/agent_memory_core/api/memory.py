import os
import yaml
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

from agent_memory_core.core.router import MemoryRouter
from agent_memory_core.core.policy import MemoryPolicy
from agent_memory_core.core.schemas import (
    MemoryEvent, MemoryDecision, ResolutionIntent, TrustBoundary, 
    DecisionContent, SEMANTIC_KINDS, KIND_DECISION, EmbeddingProvider
)
from agent_memory_core.stores.episodic import EpisodicStore
from agent_memory_core.stores.semantic import SemanticStore
from agent_memory_core.stores.vector import VectorStore
from agent_memory_core.reasoning.conflict import ConflictEngine
from agent_memory_core.reasoning.resolution import ResolutionEngine
from agent_memory_core.reasoning.decay import DecayEngine, DecayReport
from agent_memory_core.reasoning.reflection import ReflectionEngine

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
                 semantic_store: Optional[SemanticStore] = None,
                 embedding_provider: Optional[EmbeddingProvider] = None):
        """
        Initialize the memory system.
        
        :param storage_path: Base directory for all memory storage.
        :param ttl_days: Number of days before episodic memory starts to decay.
        :param trust_boundary: Security policy for determining what can be persisted.
        :param embedding_provider: Provider for generating embeddings (optional).
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
        self.vector = VectorStore(os.path.join(storage_path, "vector.db"))
        self.embedding_provider = embedding_provider
        
        self.conflict_engine = ConflictEngine(self.semantic.repo_path)
        self.resolution_engine = ResolutionEngine(self.semantic.repo_path)
        self.decay_engine = DecayEngine(ttl_days=ttl_days)
        self.reflection_engine = ReflectionEngine(self.episodic, self.semantic)
        
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
                decision.metadata["file_id"] = new_fid
                
                # Update vector index if provider is available
                if self.embedding_provider:
                    try:
                        emb = self.embedding_provider.get_embedding(f"{event.content} {getattr(event.context, 'rationale', '')}")
                        self.vector.update_index(new_fid, emb, event.content)
                    except Exception as e:
                        # Vector index is auxiliary, don't fail the whole process if it fails
                        logger.error(f"Failed to update vector index for {new_fid}: {e}")

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

    def run_reflection(self) -> List[str]:
        """
        Execute the reflection process to identify patterns and suggest improvements.
        """
        return self.reflection_engine.run_cycle()

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

    def accept_proposal(self, proposal_id: str) -> MemoryDecision:
        """
        Converts a proposal into an active semantic decision.
        """
        from agent_memory_core.stores.semantic_store.loader import MemoryLoader
        
        file_path = os.path.join(self.semantic.repo_path, proposal_id)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Proposal not found: {proposal_id}")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            data, _ = MemoryLoader.parse(f.read())
        
        if data.get("kind") != "proposal":
            raise ValueError(f"File {proposal_id} is not a proposal")
            
        ctx = data.get("context", {})
        if ctx.get("status") != "draft":
            raise ValueError(f"Proposal {proposal_id} is already {ctx.get('status')}")

        # Convert proposal to decision
        # Note: In a more advanced version, we might check if it supersedes anything
        decision = self.record_decision(
            title=ctx.get("title"),
            target=ctx.get("target"),
            rationale=f"Accepted proposal {proposal_id}. {ctx.get('rationale', '')}",
            consequences=ctx.get("suggested_consequences", [])
        )
        
        if decision.should_persist:
            new_id = decision.metadata.get("file_id")
            self.semantic.update_decision(
                proposal_id, 
                {"status": "accepted", "converted_to": new_id}, 
                commit_msg=f"Accepted and converted to {new_id}"
            )
            
        return decision

    def reject_proposal(self, proposal_id: str, reason: str):
        """
        Marks a proposal as rejected.
        """
        self.semantic.update_decision(
            proposal_id, 
            {"status": "rejected", "rejection_reason": reason}, 
            commit_msg=f"Rejected proposal: {reason}"
        )

    def search_decisions(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for relevant decisions using vector similarity.
        
        :param query: Natural language query.
        :param limit: Maximum number of results.
        :return: List of matches with scores and previews.
        """
        if not self.embedding_provider:
            return []
        
        try:
            query_emb = self.embedding_provider.get_embedding(query)
            results = self.vector.search(query_emb, limit=limit)
            
            output = []
            for doc_id, score, preview in results:
                output.append({
                    "id": doc_id,
                    "score": round(score, 4),
                    "preview": preview
                })
            return output
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

