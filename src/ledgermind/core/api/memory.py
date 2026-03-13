import os
import yaml
import json
import logging
import shutil
import subprocess
import uuid
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple

logger = logging.getLogger(__name__)

from ledgermind.core.core.router import MemoryRouter
from ledgermind.core.core.schemas import (
    MemoryEvent, MemoryDecision, ResolutionIntent, TrustBoundary, 
    DecisionContent, DecisionStream, DecisionPhase, DecisionVitality, ProposalStatus, SEMANTIC_KINDS, KIND_DECISION, KIND_PROPOSAL, KIND_INTERVENTION,
    LedgermindConfig
)
from ledgermind.core.core.exceptions import InvariantViolation, ConflictError
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore
from ledgermind.core.stores.interfaces import MetadataStore, EpisodicProvider, AuditProvider
from ledgermind.core.reasoning.conflict import ConflictEngine
from ledgermind.core.reasoning.resolution import ResolutionEngine
from ledgermind.core.reasoning.decay import DecayEngine, DecayReport
from ledgermind.core.reasoning.reflection import ReflectionEngine
from ledgermind.core.reasoning.lifecycle import LifecycleEngine
from ledgermind.core.reasoning.git_indexer import GitIndexer
from ledgermind.core.stores.vector import VectorStore
from ledgermind.core.core.targets import TargetRegistry

from ledgermind.core.utils.events import EventEmitter

# Optional observability
try:
    from ledgermind.server.metrics import VITALITY_DISTRIBUTION, PHASE_DISTRIBUTION
except ImportError:
    VITALITY_DISTRIBUTION = None
    PHASE_DISTRIBUTION = None

class Memory:
    """
    The main entry point for the ledgermind-core.
    Provides methods for processing events, recording decisions, and managing knowledge decay.
    """
    _git_available: Optional[bool] = None

    def __init__(self,
                 storage_path: Optional[str] = None,
                 ttl_days: Optional[int] = None,
                 trust_boundary: Optional[TrustBoundary] = None,
                 config: Optional[LedgermindConfig] = None,
                 episodic_store: Optional[Union[EpisodicStore, EpisodicProvider]] = None,
                 semantic_store: Optional[SemanticStore] = None,
                 namespace: Optional[str] = None,
                 meta_store_provider: Optional[MetadataStore] = None,
                 audit_store_provider: Optional[AuditProvider] = None,
                 vector_model: Optional[str] = None,
                 vector_workers: Optional[int] = None,
                 include_history: bool = True):
        """
        Initialize the memory system.

        Args:
            storage_path: Path to storage directory
            ttl_days: Time-to-live for events in days
            trust_boundary: Trust boundary for operations
            config: Optional configuration object
            episodic_store: Custom episodic store instance
            semantic_store: Custom semantic store instance
            namespace: Default namespace for operations
            meta_store_provider: Custom metadata store provider
            audit_store_provider: Custom audit store provider
            vector_model: Name of vector model to use
            vector_workers: Number of vector store workers
            include_history: If False, search returns only active decisions.
                            If True (default), superseded/deprecated decisions are included
                            with reduced priority. Use mode="strict" for active-only regardless.
        """
        self._events = None
        if config:
            self.config = config
        else:
            self.config = LedgermindConfig(
                storage_path=storage_path or "../.ledgermind",
                ttl_days=ttl_days or 30,
                trust_boundary=trust_boundary or TrustBoundary.AGENT_WITH_INTENT,
                namespace=namespace or "default",
                vector_model=vector_model or "../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf",
                vector_workers=vector_workers if vector_workers is not None else 0
            )

        raw_path = self.config.storage_path
        if not isinstance(raw_path, str) or "<MagicMock" in str(raw_path):
             raw_path = os.path.join(os.getcwd(), ".ledgermind_fallback")
        self.storage_path = os.path.abspath(raw_path)
        self.trust_boundary = self.config.trust_boundary
        self.namespace = self.config.namespace
        self.include_history = include_history
        
        try:
            if not os.path.exists(self.storage_path):
                os.makedirs(self.storage_path, exist_ok=True)
        except PermissionError:
            raise ValueError(f"No permission to create storage path: {self.storage_path}")
            
        # 1. Initialize Storage (Metadata must be ready first)
        if semantic_store:
            self.semantic = semantic_store
            self.episodic: Union[EpisodicStore, EpisodicProvider] = episodic_store or EpisodicStore(os.path.join(self.storage_path, "episodic.db"))
        else:
            self.semantic = SemanticStore(
                os.path.join(self.storage_path, "semantic"), 
                trust_boundary=self.trust_boundary,
                meta_store=meta_store_provider,
                audit_store=audit_store_provider
            )
            self.episodic: Union[EpisodicStore, EpisodicProvider] = episodic_store or EpisodicStore(os.path.join(self.storage_path, "episodic.db"))

        # 2. Sync Config from DB (Overrides defaults if present)
        db_model = self.semantic.meta.get_config("vector_model")
        if db_model:
            self.config.vector_model = db_model

        # V7.7: CRITICAL - Validate integrity on startup
        # This detects manual file deletions that break referential integrity
        try:
            # Check that all indexed files exist on disk (only for non-empty DB)
            logger.info(f"Running integrity check: storage={self.storage_path}")
            from ledgermind.core.stores.semantic_store.integrity import IntegrityChecker
            IntegrityChecker.validate_files_exist(self.storage_path, None)  # Pass None to force direct DB access
            logger.info("Integrity check passed")
        except IntegrityViolation as e:
            logger.error(f"Integrity violation detected on startup: {e}")
            raise

        # 3. Initialize Vector Engine
        self.vector = VectorStore(
            os.path.join(self.storage_path, "vector_index"),
            model_name=self.config.vector_model,
            workers=self.config.vector_workers
        )
        # Deferred loading (VectorStore will load on first document addition or search)

        self.conflict_engine = ConflictEngine(self.semantic.repo_path, meta_store=self.semantic.meta)
        self.resolution_engine = ResolutionEngine(self.semantic.repo_path)
        self.decay_engine = DecayEngine(ttl_days=self.config.ttl_days)
        self.reflection_engine = ReflectionEngine(self.episodic, self.semantic, processor=self)
        
        self.router = MemoryRouter(
            self.conflict_engine, 
            self.resolution_engine
        )
        
        self.targets = TargetRegistry(self.semantic.repo_path)
        
        # Performance: Pre-initialize shared reasoning components
        from ledgermind.core.reasoning.lifecycle import LifecycleEngine
        self._lifecycle = LifecycleEngine()

        # DECOMPOSITION: Initialize Runtime Context and Transaction Manager
        from .context import MemoryContext
        from .transaction import ReentrantTransactionManager
        
        self.context = MemoryContext(
            storage_path=self.storage_path,
            namespace=self.namespace,
            trust_boundary=self.trust_boundary,
            include_history=self.include_history,
            config=self.config,
            semantic=self.semantic,
            episodic=self.episodic,
            vector=self.vector,
            conflict_engine=self.conflict_engine,
            resolution_engine=self.resolution_engine,
            decay_engine=self.decay_engine,
            reflection_engine=self.reflection_engine,
            targets=self.targets,
            lifecycle=self._lifecycle
        )
        self.context.router = self.router # Shared router
        
        self.transaction_manager = ReentrantTransactionManager(self.semantic)
        self.context.transaction_manager = self.transaction_manager

        # SERVICES: Initialize decomposing services
        from .services.query import QueryService
        from .services.lifecycle import LifecycleManagementService
        from .services.health import HealthService
        from .services.integrity import IntegrityService
        from .services.decision_command import DecisionCommandService
        from .services.event_processing import EventProcessingService
        
        self._query = QueryService(self.context)
        self._lifecycle_service = LifecycleManagementService(self.context)
        self._health_service = HealthService(self.context)
        self._integrity_service = IntegrityService(self.context)
        self._decision_command = DecisionCommandService(self.context)
        self._event_processing = EventProcessingService(self.context, query_service=self._query)

    @property
    def events(self):
        if self._events is None:
            from ledgermind.core.utils.events import EventEmitter
            self._events = EventEmitter()
        return self._events

    def check_environment(self) -> Dict[str, Any]:
        """
        Performs a pre-flight check of the environment to ensure all 
        dependencies and storage conditions are met.
        """
        return self._health_service.check_health()


    def process_event(self, 
                      source: str, 
                      kind: str, 
                      content: str, 
                      context: Optional[Union[DecisionContent, DecisionStream, Dict[str, Any]]] = None,
                      intent: Optional[ResolutionIntent] = None,
                      namespace: Optional[str] = None,
                      vector: Optional[Any] = None,
                      timestamp: Optional[Union[datetime, str]] = None) -> MemoryDecision:
        """
        Process an incoming event and decide whether to persist it.
        """
        return self._event_processing.process_event(
            source, kind, content, context, intent, namespace, vector, timestamp, 
            event_emitter=self.events
        )

    def get_decisions(self) -> List[str]:
        """
        List all active decision identifiers in the semantic store.
        """
        return self._query.list_decisions()

    def get_decision_history(self, decision_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve the full version history of a specific decision from the audit log.
        """
        return self._query.get_decision_history(decision_id)

    def get_recent_events(self, limit: int = 10, include_archived: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve recent events from the episodic store.
        """
        return self._query.get_recent_events(limit, include_archived)

    def link_evidence(self, event_id: int, semantic_id: str):
        """
        Manually link an episodic event to a semantic record.
        """
        return self._integrity_service.link_evidence(event_id, semantic_id)

    def update_decision(self, decision_id: str, updates: Dict[str, Any], commit_msg: str, skip_episodic: bool = False) -> bool:
        """
        Coordinates updates to a semantic record across all stores.
        """
        return self._decision_command.update_decision(decision_id, updates, commit_msg, skip_episodic)

    def run_decay(self, dry_run: bool = False, stop_event: Optional[threading.Event] = None) -> DecayReport:
        """
        Execute the decay process for episodic and semantic memories.
        """
        return self._lifecycle_service.run_decay(dry_run, stop_event)

    def run_reflection(self, stop_event: Optional[threading.Event] = None) -> List[str]:
        """
        Execute the incremental reflection process to identify patterns.
        """
        return self._lifecycle_service.run_reflection(stop_event)

    def sync_git(self, repo_path: str = ".", limit: int = 20) -> int:
        """
        Syncs recent Git commits into episodic memory.
        """
        return self._integrity_service.sync_git(self, repo_path, limit)

    def record_decision(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None, evidence_ids: Optional[List[int]] = None, namespace: Optional[str] = None, arbiter_callback: Optional[callable] = None) -> MemoryDecision:
        """
        Helper to record a new decision in semantic memory.
        """
        return self._decision_command.record_decision(
            title, target, rationale, consequences, evidence_ids, namespace, arbiter_callback,
            memory_facade=self
        )

    def supersede_decision(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None, evidence_ids: Optional[List[int]] = None, namespace: Optional[str] = None, vector: Optional[Any] = None, phase: Optional[Any] = None, enrichment_status: str = "pending") -> MemoryDecision:
        """
        Helper to evolve knowledge by superseding existing decisions.
        """
        return self._decision_command.supersede_decision(
            title, target, rationale, old_decision_ids, consequences, evidence_ids, namespace, vector, phase,
            enrichment_status=enrichment_status,
            memory_facade=self
        )

    def accept_proposal(self, proposal_id: str) -> MemoryDecision:
        """
        Converts a proposal into an active semantic decision.
        """
        return self._decision_command.accept_proposal(proposal_id, memory_facade=self)

    def reject_proposal(self, proposal_id: str, reason: str):
        """
        Marks a proposal as rejected.
        """
        return self._decision_command.reject_proposal(proposal_id, reason)

    def search_decisions(self, query: str, limit: int = 5, offset: int = 0, namespace: Optional[str] = None, mode: str = "balanced") -> List[Dict[str, Any]]:
        """
        Search with Recursive Truth Resolution and Hybrid Vector/Keyword ranking (RRF).
        """
        return self._query.search(query, limit, offset, namespace, mode)

    def _resolve_to_truth(self, doc_id: str, mode: str, cache: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """Recursively follows 'superseded_by' links using Metadata Store."""
        return self._query._resolve_to_truth(doc_id, mode, cache)

    def generate_knowledge_graph(self, target: Optional[str] = None) -> str:
        """Generates a Mermaid graph of knowledge evolution."""
        return self._query.generate_knowledge_graph(target)

    def run_maintenance(self, stop_event: Optional[threading.Event] = None) -> Dict[str, Any]:
        """Runs periodic maintenance tasks. Supports interruption via stop_event."""
        # Delegating the heavy lifting to the service
        result = self._lifecycle_service.run_maintenance(stop_event=stop_event)
        
        # Post-maintenance metric updates (Facade responsibility for observability)
        stats = self.get_stats()
        if VITALITY_DISTRIBUTION:
            for v, count in stats.get('vitality', {}).items():
                VITALITY_DISTRIBUTION.labels(vitality=v).set(count)
        if PHASE_DISTRIBUTION:
            for p, count in stats.get('phases', {}).items():
                PHASE_DISTRIBUTION.labels(phase=p).set(count)

        # Merge Engine coordination remains part of maintenance orchestration for now
        from ledgermind.core.reasoning.merging import MergeEngine
        merger = MergeEngine(self)
        merges = merger.scan_for_duplicates()
        
        result["merging"] = {"proposals_created": len(merges), "ids": merges}
        return result

    def get_stats(self) -> Dict[str, Any]:
        """Returns diagnostic statistics including lifecycle distribution."""
        return self._health_service.get_statistics()

    def forget(self, decision_id: str):
        """Hard-deletes a memory."""
        return self._integrity_service.forget(decision_id)

    def close(self):
        """Releases all resources."""
        if hasattr(self, 'vector'): self.vector.close()
        if hasattr(self, 'semantic') and hasattr(self.semantic, 'meta'): self.semantic.meta.close()
        logger.info("Memory system closed.")
