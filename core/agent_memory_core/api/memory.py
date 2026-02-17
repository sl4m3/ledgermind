import os
import yaml
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple

logger = logging.getLogger(__name__)

from agent_memory_core.core.router import MemoryRouter
from agent_memory_core.core.schemas import (
    MemoryEvent, MemoryDecision, ResolutionIntent, TrustBoundary, 
    DecisionContent, SEMANTIC_KINDS, KIND_DECISION, KIND_PROPOSAL
)
from agent_memory_core.core.exceptions import InvariantViolation, ConflictError
from agent_memory_core.stores.episodic import EpisodicStore
from agent_memory_core.stores.semantic import SemanticStore
from agent_memory_core.stores.interfaces import MetadataStore, EpisodicProvider, AuditProvider
from agent_memory_core.reasoning.conflict import ConflictEngine
from agent_memory_core.reasoning.resolution import ResolutionEngine
from agent_memory_core.reasoning.decay import DecayEngine, DecayReport
from agent_memory_core.reasoning.reflection import ReflectionEngine
from agent_memory_core.reasoning.git_indexer import GitIndexer
from agent_memory_core.stores.vector import VectorStore

class Memory:
    """
    The main entry point for the agent-memory-core.
    Provides methods for processing events, recording decisions, and managing knowledge decay.
    """
    def __init__(self, 
                 storage_path: str = "./memory", 
                 ttl_days: int = 30, 
                 trust_boundary: TrustBoundary = TrustBoundary.AGENT_WITH_INTENT,
                 episodic_store: Optional[Union[EpisodicStore, EpisodicProvider]] = None,
                 semantic_store: Optional[SemanticStore] = None,
                 namespace: Optional[str] = None,
                 meta_store_provider: Optional[MetadataStore] = None,
                 audit_store_provider: Optional[AuditProvider] = None,
                 vector_model: str = "all-MiniLM-L6-v2"):
        """
        Initialize the memory system.
        
        :param storage_path: Base directory for all memory storage.
        :param ttl_days: Number of days before episodic memory starts to decay.
        :param trust_boundary: Security policy for determining what can be persisted.
        """
        self.storage_path = storage_path
        self.trust_boundary = trust_boundary
        self.namespace = namespace or "default"
        
        try:
            if not os.path.exists(storage_path):
                os.makedirs(storage_path, exist_ok=True)
        except PermissionError:
            raise ValueError(f"No permission to create storage path: {storage_path}")
            
        # Pluggable Storage Logic
        if semantic_store:
            self.semantic = semantic_store
            self.episodic: Union[EpisodicStore, EpisodicProvider] = episodic_store or EpisodicStore(os.path.join(storage_path, "episodic.db"))
        else:
            self.semantic = SemanticStore(
                os.path.join(storage_path, "semantic"), 
                trust_boundary=trust_boundary,
                meta_store=meta_store_provider,
                audit_store=audit_store_provider
            )
            self.episodic: Union[EpisodicStore, EpisodicProvider] = episodic_store or EpisodicStore(os.path.join(storage_path, "episodic.db"))

        self.vector = VectorStore(
            os.path.join(storage_path, "vector_index"),
            model_name=vector_model
        )
        self.vector.load()

        self.conflict_engine = ConflictEngine(self.semantic.repo_path, meta_store=self.semantic.meta)
        self.resolution_engine = ResolutionEngine(self.semantic.repo_path)
        self.decay_engine = DecayEngine(ttl_days=ttl_days)
        self.reflection_engine = ReflectionEngine(self.episodic, self.semantic)
        
        self.router = MemoryRouter(
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
        
        # 2.5: Prevent duplicate processing
        if self.episodic.find_duplicate(event):
            return MemoryDecision(
                should_persist=False,
                store_type="none",
                reason="Duplicate event detected"
            )
        
        decision = self.router.route(event, intent=intent)
        
        if decision.should_persist:
            if decision.store_type == "episodic":
                self.episodic.append(event)
            elif decision.store_type == "semantic":
                # Use Transaction for atomic save + status updates
                with self.semantic.transaction():
                    # 1. Update back-links and deactivate old versions BEFORE saving new one
                    # to satisfy SQLite UNIQUE constraint on active targets.
                    if intent and intent.resolution_type == "supersede":
                        for old_id in intent.target_decision_ids:
                            self.semantic.update_decision(
                                old_id, 
                                {"status": "superseded"},
                                commit_msg=f"Deactivating for transition"
                            )

                    # 2. Prepare context for new decision
                    if intent and intent.resolution_type == "supersede" and isinstance(event.context, DecisionContent):
                        event.context.supersedes = intent.target_decision_ids
                    
                    # 3. Save new decision (this updates SQLite and Git)
                    new_fid = self.semantic.save(event)
                    decision.metadata["file_id"] = new_fid
                    
                    # 3.5: Index in VectorStore
                    try:
                        self.vector.add_documents([{
                            "id": new_fid,
                            "content": event.content
                        }])
                    except Exception as ve:
                        logger.warning(f"Vector indexing failed for {new_fid}: {ve}")

                    # 4. Now that we have new_fid, update back-links properly
                    if intent and intent.resolution_type == "supersede":
                        for old_id in intent.target_decision_ids:
                            self.semantic.update_decision(
                                old_id, 
                                {"status": "superseded", "superseded_by": new_fid},
                                commit_msg=f"Superseded by {new_fid}"
                            )

                # Immortal Link (after transaction success)
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

    def sync_git(self, repo_path: str = ".", limit: int = 20) -> int:
        """
        Syncs recent Git commits into episodic memory.
        """
        indexer = GitIndexer(repo_path)
        return indexer.index_to_memory(self, limit=limit)

    def record_decision(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> MemoryDecision:
        """
        Helper to record a new decision in semantic memory.
        Raises:
            ConflictError: If target already has an active decision.
            InvariantViolation: If other invariants are violated.
        """
        ctx = {
            "title": title,
            "target": target,
            "status": "active",
            "rationale": rationale,
            "consequences": consequences or []
        }
        decision = self.process_event(
            source="agent",
            kind=KIND_DECISION,
            content=title,
            context=ctx
        )
        
        if not decision.should_persist:
            if "CONFLICT" in decision.reason:
                raise ConflictError(decision.reason)
            raise InvariantViolation(f"Failed to record decision: {decision.reason}")
            
        return decision

    def supersede_decision(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> MemoryDecision:
        """
        Helper to evolve knowledge by superseding existing decisions.
        Raises:
            ConflictError: If resolution intent is invalid or incomplete.
            InvariantViolation: If other invariants are violated.
        """
        active_files = self.semantic.list_active_conflicts(target)
        for oid in old_decision_ids:
            if oid not in active_files:
                raise ConflictError(f"Cannot supersede {oid}: it is no longer active for target {target}")

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
        decision = self.process_event(
            source="agent",
            kind=KIND_DECISION,
            content=title,
            context=ctx,
            intent=intent
        )

        if not decision.should_persist:
            if "CONFLICT" in decision.reason:
                raise ConflictError(decision.reason)
            raise InvariantViolation(f"Failed to supersede decision: {decision.reason}")
            
        return decision

    def accept_proposal(self, proposal_id: str) -> MemoryDecision:
        """
        Converts a proposal into an active semantic decision.
        """
        self.semantic._validate_fid(proposal_id)
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
        with self.semantic.transaction():
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
        self.semantic._validate_fid(proposal_id)
        self.semantic.update_decision(
            proposal_id, 
            {"status": "rejected", "rejection_reason": reason}, 
            commit_msg=f"Rejected proposal: {reason}"
        )

    def search_decisions(self, query: str, limit: int = 5, mode: str = "balanced") -> List[Dict[str, Any]]:
        """
        Search with Recursive Truth Resolution and Hybrid Vector/Keyword ranking.
        """
        # 1. Try Vector Search first
        vector_results = []
        try:
            vector_results = self.vector.search(query, limit=limit * 3)
        except Exception as e:
            logger.debug(f"Vector search bypassed: {e}")

        candidates = []
        seen_ids = set()

        # 2. Process Vector Candidates
        for item in vector_results:
            fid = item['id']
            final_id, data = self._resolve_to_truth(fid, mode)
            if not data or final_id in seen_ids: continue
            
            ctx = data.get("context", {})
            status = ctx.get("status", "unknown")
            if mode == "strict" and status != "active": continue
                
            candidates.append({
                "id": final_id,
                "score": item['score'],
                "status": status,
                "title": ctx.get("title", "unknown"),
                "target": ctx.get("target", "unknown"),
                "preview": data.get("content", fid)[:200],
                "kind": data.get("kind"),
                "is_active": (status == "active")
            })
            seen_ids.add(final_id)

        # 3. Fallback to keyword search if we need more results
        if len(candidates) < limit:
            raw_keyword = self.semantic.meta.keyword_search(query, limit=limit * 2)
            for item in raw_keyword:
                fid = item['fid']
                final_id, data = self._resolve_to_truth(fid, mode)
                if not data or final_id in seen_ids: continue
                
                ctx = data.get("context", {})
                status = ctx.get("status", "unknown")
                if mode == "strict" and status != "active": continue
                    
                candidates.append({
                    "id": final_id,
                    "score": 0.5, # Lower default score for keyword matches
                    "status": status,
                    "title": ctx.get("title", "unknown"),
                    "target": ctx.get("target", "unknown"),
                    "preview": data.get("content", fid)[:200],
                    "kind": data.get("kind"),
                    "is_active": (status == "active")
                })
                seen_ids.add(final_id)
            
        return candidates[:limit]


    def _resolve_to_truth(self, doc_id: str, mode: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Recursively follows 'superseded_by' links to find the latest version."""
        self.semantic._validate_fid(doc_id)
        from agent_memory_core.stores.semantic_store.loader import MemoryLoader
        current_id = doc_id
        depth = 0
        while depth < 5:
            file_path = os.path.join(self.semantic.repo_path, current_id)
            if not os.path.exists(file_path): return current_id, None
            with open(file_path, 'r', encoding='utf-8') as f:
                data, _ = MemoryLoader.parse(f.read())
            status = data.get("context", {}).get("status")
            successor = data.get("context", {}).get("superseded_by")
            if mode == "audit" or status == "active" or not successor:
                return current_id, data
            current_id = successor
            depth += 1
        return current_id, None

    def generate_knowledge_graph(self, target: Optional[str] = None) -> str:
        """Generates a Mermaid graph of knowledge evolution."""
        from agent_memory_core.reasoning.ranking.graph import KnowledgeGraphGenerator
        generator = KnowledgeGraphGenerator(self.semantic.repo_path, self.semantic.meta)
        return generator.generate_mermaid(target_filter=target)

    def run_maintenance(self) -> Dict[str, Any]:
        """Runs periodic maintenance tasks: decay and merge analysis."""
        decay_report = self.run_decay()
        from agent_memory_core.reasoning.merging import MergeEngine
        merger = MergeEngine(self)
        merges = merger.scan_for_duplicates()
        return {
            "decay": decay_report.__dict__,
            "merging": {"proposals_created": len(merges), "ids": merges}
        }

    def get_stats(self) -> Dict[str, Any]:
        """Returns diagnostic statistics about memory system health."""
        active_semantic = len(self.get_decisions())
        return {
            "semantic_decisions": active_semantic,
            "namespace": self.namespace,
            "storage_path": self.storage_path
        }

    def forget(self, decision_id: str):
        """Hard-deletes a memory from filesystem and metadata."""
        self.semantic._validate_fid(decision_id)
        self.semantic.purge_memory(decision_id)
        logger.info(f"Memory {decision_id} forgotten across systems.")

