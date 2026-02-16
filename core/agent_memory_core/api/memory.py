import os
import yaml
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple

logger = logging.getLogger(__name__)

from agent_memory_core.core.router import MemoryRouter
from agent_memory_core.core.policy import MemoryPolicy
from agent_memory_core.core.schemas import (
    MemoryEvent, MemoryDecision, ResolutionIntent, TrustBoundary, 
    DecisionContent, SEMANTIC_KINDS, KIND_DECISION, KIND_PROPOSAL, EmbeddingProvider
)
from agent_memory_core.core.exceptions import InvariantViolation, ConflictError
from agent_memory_core.stores.episodic import EpisodicStore
from agent_memory_core.stores.semantic import SemanticStore
from agent_memory_core.stores.vector import VectorStore
from agent_memory_core.stores.interfaces import MetadataStore, VectorProvider, EpisodicProvider, AuditProvider
from agent_memory_core.reasoning.conflict import ConflictEngine
from agent_memory_core.reasoning.resolution import ResolutionEngine
from agent_memory_core.reasoning.decay import DecayEngine, DecayReport
from agent_memory_core.reasoning.reflection import ReflectionEngine
from agent_memory_core.reasoning.git_indexer import GitIndexer
from agent_memory_core.reasoning.ranking.policy import RankingPolicy
from agent_memory_core.core.telemetry import trace_and_time, update_decision_metrics, SEARCH_QUALITY
from agent_memory_core.core.compliance import PIIMasker, MemoryEncryptor
from agent_memory_core.core.events import MemoryEventEmitter, RedisPubSubProvider
from agent_memory_core.core.optimization import EmbeddingCache, CachingEmbeddingProvider, VectorCompressor

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
                 embedding_provider: Optional[EmbeddingProvider] = None,
                 db_url: Optional[str] = None,
                 namespace: Optional[str] = None,
                 encryption_key: Optional[str] = None,
                 mask_pii: bool = True,
                 meta_store_provider: Optional[MetadataStore] = None,
                 audit_store_provider: Optional[AuditProvider] = None,
                 pubsub_url: Optional[str] = None):
        """
        Initialize the memory system.
        
        :param storage_path: Base directory for all memory storage.
        :param ttl_days: Number of days before episodic memory starts to decay.
        :param trust_boundary: Security policy for determining what can be persisted.
        :param embedding_provider: Provider for generating embeddings (optional).
        :param pubsub_url: Redis URL for multi-instance synchronization.
        """
        self.storage_path = storage_path
        self.trust_boundary = trust_boundary
        self.namespace = namespace or "default"
        self.mask_pii = mask_pii
        self.encryptor = MemoryEncryptor(encryption_key)
        self.events = MemoryEventEmitter()
        
        # Optimization state
        self.embedding_cache = None
        self.compressor = VectorCompressor()
        self.config_options = {
            "embedding_cache": False,
            "deduplication": True,
            "compression": None
        }

        if pubsub_url:
            self.pubsub = RedisPubSubProvider(pubsub_url)
            # Sync internal events with Redis updates from other instances
            try:
                loop = asyncio.get_running_loop()
                async def on_redis_update(data):
                    await self.events.emit("remote_memory_changed", data)
                loop.create_task(self.pubsub.subscribe("agent_memory_updates", on_redis_update))
            except RuntimeError: pass # Loop not yet running
        else:
            self.pubsub = None
        
        try:
            if not os.path.exists(storage_path):
                os.makedirs(storage_path, exist_ok=True)
        except PermissionError:
            raise ValueError(f"No permission to create storage path: {storage_path}")
            
        self.policy = MemoryPolicy()
        
        # Pluggable Storage Logic
        if semantic_store:
            self.semantic = semantic_store
            self.vector: VectorProvider = VectorStore(os.path.join(storage_path, "vector.db")) # Default vector
            self.episodic: Union[EpisodicStore, EpisodicProvider] = episodic_store or EpisodicStore(os.path.join(storage_path, "episodic.db"))
        elif db_url:
            from agent_memory_core.stores.postgres import PostgresStore
            pg_store = PostgresStore(db_url)
            self.semantic = SemanticStore(
                os.path.join(storage_path, "semantic"), 
                trust_boundary=trust_boundary,
                meta_store=pg_store,
                audit_store=audit_store_provider
            )
            self.vector: VectorProvider = pg_store
            self.episodic: Union[EpisodicStore, EpisodicProvider] = pg_store
        else:
            self.semantic = SemanticStore(
                os.path.join(storage_path, "semantic"), 
                trust_boundary=trust_boundary,
                meta_store=meta_store_provider,
                audit_store=audit_store_provider
            )
            # Pass compressor to SQLite VectorStore
            self.vector: VectorProvider = VectorStore(os.path.join(storage_path, "vector.db"), compressor=self.compressor)
            self.episodic: Union[EpisodicStore, EpisodicProvider] = episodic_store or EpisodicStore(os.path.join(storage_path, "episodic.db"))

        self.embedding_provider = embedding_provider
        
        self.conflict_engine = ConflictEngine(self.semantic.repo_path, meta_store=self.semantic.meta)
        self.resolution_engine = ResolutionEngine(self.semantic.repo_path)
        self.decay_engine = DecayEngine(ttl_days=ttl_days)
        self.reflection_engine = ReflectionEngine(self.episodic, self.semantic)
        
        self.router = MemoryRouter(
            self.policy, 
            self.conflict_engine, 
            self.resolution_engine
        )

    def configure(self, embedding_cache: bool = True, deduplication: bool = True, compression: Optional[str] = "zstd"):
        """
        Dynamically configures memory optimization settings.
        """
        self.config_options.update({
            "embedding_cache": embedding_cache,
            "deduplication": deduplication,
            "compression": compression
        })
        
        if embedding_cache and not self.embedding_cache:
            cache_path = os.path.join(self.storage_path, "embedding_cache.db")
            self.embedding_cache = EmbeddingCache(cache_path)
            if self.embedding_provider:
                self.embedding_provider = CachingEmbeddingProvider(self.embedding_provider, self.embedding_cache)
        
        logger.info(f"Memory configured with optimization: {self.config_options}")

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

        # Apply Privacy Controls
        safe_content = content
        if self.mask_pii:
            safe_content = PIIMasker.mask(content)
        
        # Build and Validate event
        event = MemoryEvent(
            source=source,
            kind=kind,
            content=safe_content,
            context=context or {}
        )
        
        # Apply Encryption at Rest
        if self.encryptor.fernet:
            # We encrypt the rationale and body content before it reaches SemanticStore
            if hasattr(event.context, 'rationale'):
                event.context.rationale = self.encryptor.encrypt(event.context.rationale)
            elif isinstance(event.context, dict) and 'rationale' in event.context:
                event.context['rationale'] = self.encryptor.encrypt(event.context['rationale'])
        
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
                    
                    # 4. Now that we have new_fid, update back-links properly
                    if intent and intent.resolution_type == "supersede":
                        for old_id in intent.target_decision_ids:
                            self.semantic.update_decision(
                                old_id, 
                                {"status": "superseded", "superseded_by": new_fid},
                                commit_msg=f"Superseded by {new_fid}"
                            )

                    # 5. Update vector index if provider is available
                    if self.embedding_provider:
                        try:
                            # Use trace_and_time for telemetry if needed
                            emb = self.embedding_provider.get_embedding(f"{event.content} {getattr(event.context, 'rationale', '') if hasattr(event.context, 'rationale') else (event.context.get('rationale', '') if isinstance(event.context, dict) else '')}")
                            self.vector.update_index(new_fid, emb, event.content)
                        except Exception as e:
                            logger.error(f"Failed to update vector index for {new_fid}: {e}")
                
                # Immortal Link (after transaction success)
                self.episodic.append(event, linked_id=new_fid)
                
                # Notify via PubSub if available
                if self.pubsub:
                    asyncio.create_task(self.pubsub.publish("agent_memory_updates", {
                        "action": "saved",
                        "id": new_fid,
                        "kind": event.kind,
                        "namespace": self.namespace
                    }))
                
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

        # PI1 Enforcement: Review Window (1 hour for AI-generated proposals)
        if data.get("source") == "reflection_engine":
            from datetime import timedelta
            created_at = datetime.fromisoformat(ctx.get("first_observed_at"))
            if datetime.now() - created_at < timedelta(hours=1):
                raise PermissionError(f"PI1 Violation: Proposal {proposal_id} is in Review Window (1h required)")

        # Convert proposal to decision
        # Note: In a more advanced version, we might check if it supersedes anything
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
        self.semantic.update_decision(
            proposal_id, 
            {"status": "rejected", "rejection_reason": reason}, 
            commit_msg=f"Rejected proposal: {reason}"
        )

    def search_decisions(self, query: str, limit: int = 5, mode: str = "balanced") -> List[Dict[str, Any]]:
        """
        Hybrid Search with Recursive Truth Resolution and Target Deduplication.
        Falls back to keyword search if embeddings are unavailable.
        """
        if not self.embedding_provider:
            # Fallback to metadata-only keyword search
            raw_results = self.semantic.meta.keyword_search(query, limit=limit * 2)
            candidates = []
            for item in raw_results:
                fid = item['fid']
                final_id, data = self._resolve_to_truth(fid, mode)
                if not data: continue
                candidates.append({
                    "id": final_id,
                    "score": 0.5, # Static score for keyword match
                    "status": item['status'],
                    "target": item['target'],
                    "preview": data.get("content", fid)[:200],
                    "kind": item['kind'],
                    "is_active": (item['status'] == "active")
                })
            return candidates[:limit]
        
        try:
            query_emb = self.embedding_provider.get_embedding(query)
            raw_results = self.vector.search(query_emb, limit=limit * 5)
            
            candidates = []
            for doc_id, vector_score, preview in raw_results:
                try:
                    final_id, data = self._resolve_to_truth(doc_id, mode)
                    if not data: continue
                        
                    ctx = data.get("context", {})
                    status = ctx.get("status", "unknown")
                    target = ctx.get("target", "unknown")
                    
                    if mode == "strict" and status != "active":
                        continue
                    
                    final_score = RankingPolicy.calculate_score(
                        vector_score=vector_score,
                        metadata=ctx,
                        timestamp=datetime.fromisoformat(data.get("timestamp")) if data.get("timestamp") else None
                    )
                        
                    candidates.append({
                        "id": final_id,
                        "score": final_score,
                        "status": status,
                        "target": target,
                        "preview": data.get("content", preview)[:200],
                        "kind": data.get("kind"),
                        "is_active": (status == "active")
                    })
                except Exception: continue
            
            if mode == "audit":
                final_list = candidates
            else:
                unique_results = {}
                for c in sorted(candidates, key=lambda x: x['score'], reverse=True):
                    target = c['target']
                    if target not in unique_results:
                        unique_results[target] = c
                    elif c['is_active'] and not unique_results[target]['is_active']:
                        unique_results[target] = c
                final_list = list(unique_results.values())
            
            final_list.sort(key=lambda x: x['score'], reverse=True)
            return final_list[:limit]
        except Exception as e:
            logger.error(f"Hybrid Search failed: {e}")
            return []

    def _resolve_to_truth(self, doc_id: str, mode: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Recursively follows 'superseded_by' links to find the latest version."""
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

    def detect_drift(self, days: int = 30) -> List[Dict[str, Any]]:
        """Identifies knowledge areas with high frequency of change."""
        all_meta = self.semantic.meta.list_all()
        target_counts = {}
        for m in all_meta:
            target = m.get('target', 'unknown')
            target_counts[target] = target_counts.get(target, 0) + 1
        drifts = []
        for target, count in target_counts.items():
            if count >= 3:
                drifts.append({"target": target, "versions": count, "stability": "low"})
        return drifts

    def forget(self, decision_id: str):
        """Hard-deletes a memory from filesystem, index, and metadata."""
        self.semantic.purge_memory(decision_id)
        self.vector.delete_from_index(decision_id)
        logger.info(f"Memory {decision_id} forgotten across systems.")
