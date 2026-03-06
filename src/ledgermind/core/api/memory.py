import os
import yaml
import json
import logging
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple

logger = logging.getLogger(__name__)

from ledgermind.core.core.router import MemoryRouter
from ledgermind.core.core.schemas import (
    MemoryEvent, MemoryDecision, ResolutionIntent, TrustBoundary, 
    DecisionContent, DecisionStream, ProposalContent, DecisionPhase, DecisionVitality, ProposalStatus, SEMANTIC_KINDS, KIND_DECISION, KIND_PROPOSAL, KIND_INTERVENTION,
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

        self.storage_path = os.path.abspath(self.config.storage_path)
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
        results = {
            "git_available": False,
            "git_configured": False,
            "storage_writable": False,
            "disk_space_ok": False,
            "repo_healthy": False,
            "vector_available": False,
            "storage_locked": False,
            "lock_owner": None,
            "errors": [],
            "warnings": []
        }
        
        # 0. Check Lock Status
        results["storage_locked"] = False
        try:
            # Try to acquire the lock non-blockingly (timeout=0)
            # If it fails, then it's truly locked by another process
            if not self.semantic._fs_lock.acquire(exclusive=False, timeout=0):
                results["storage_locked"] = True
                try:
                    lock_path = self.semantic.lock_file
                    with open(lock_path, 'r') as f:
                        results["lock_owner"] = f.read().strip()
                except Exception:
                    pass
                results["warnings"].append(f"Storage is currently locked by PID: {results['lock_owner'] or 'unknown'}")
            else:
                # If we acquired it, we must release it immediately
                self.semantic._fs_lock.release()
        except Exception as e:
            # If fcntl or other lock mechanism fails, we might still have a stale lock file
            # but we shouldn't necessarily report it as 'locked' if we can't verify.
            logger.debug(f"Lock check failed: {e}")

        # 0.1 Check Vector Search (Optional)
        logger.debug("Checking vector search availability...")
        from ledgermind.core.stores.vector import _is_transformers_available, _is_llama_available, EMBEDDING_AVAILABLE, LLAMA_AVAILABLE
        
        config = getattr(self, 'config', None)
        from ledgermind.core.core.schemas import LedgermindConfig
        default_config = LedgermindConfig()
        vector_model = config.vector_model if config else default_config.vector_model
        is_gguf = vector_model.endswith(".gguf")
        
        # Only trigger lazy check for the engine we actually intend to use
        if is_gguf:
            llama_avail = LLAMA_AVAILABLE if LLAMA_AVAILABLE is not None else _is_llama_available()
            results["vector_available"] = llama_avail
            if not llama_avail:
                results["warnings"].append("llama-cpp-python not installed. GGUF vector search is disabled.")
            elif not os.path.exists(vector_model):
                results["warnings"].append(f"GGUF model missing from {vector_model}. It will be downloaded on first use.")
        else:
            transformers_avail = EMBEDDING_AVAILABLE if EMBEDDING_AVAILABLE is not None else _is_transformers_available()
            results["vector_available"] = transformers_avail
            if not transformers_avail:
                results["warnings"].append("Sentence-transformers not installed. Vector search is disabled.")

        # 1. Check Git
        if Memory._git_available is None:
            try:
                subprocess.run(["git", "--version"], capture_output=True, check=True) # nosec B603 B607
                Memory._git_available = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                Memory._git_available = False
        
        results["git_available"] = Memory._git_available
        if not results["git_available"]:
            results["errors"].append("Git is not installed or not in PATH. Semantic storage will fail.")
        else:
            # Check git config
            try:
                name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip() # nosec B603 B607
                email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip() # nosec B603 B607
                if name and email:
                    results["git_configured"] = True
                else:
                    results["warnings"].append("Git user.name or user.email not configured. Commits will use defaults.")
            except Exception:
                # Configuration check is non-critical, we can ignore errors here
                pass
            
        # 2. Check Storage Permissions and Disk Space
        if os.path.exists(self.storage_path):
            if os.access(self.storage_path, os.W_OK):
                results["storage_writable"] = True
                
                # Check disk space (require at least 50MB for healthy operation)
                try:
                    usage = shutil.disk_usage(self.storage_path)
                    free_mb = usage.free / (1024 * 1024)
                    if free_mb > 50:
                        results["disk_space_ok"] = True
                    else:
                        results["warnings"].append(f"Low disk space: {free_mb:.1f}MB available.")
                except Exception:
                    results["disk_space_ok"] = True # Fallback if disk_usage fails
            else:
                results["errors"].append(f"Storage path is not writable: {self.storage_path}")
        else:
            try:
                os.makedirs(self.storage_path, exist_ok=True)
                results["storage_writable"] = True
                results["disk_space_ok"] = True
            except Exception as e:
                results["errors"].append(f"Failed to create storage path: {e}")
                
        # 3. Check Repo Health (if audit is git)
        from ledgermind.core.stores.audit_git import GitAuditProvider
        if isinstance(self.semantic.audit, GitAuditProvider):
            try:
                self.semantic.audit.initialize()
                results["repo_healthy"] = True
            except Exception as e:
                results["errors"].append(f"Git repository initialization failed: {e}")
                
        if results["errors"] and self.trust_boundary == TrustBoundary.AGENT_WITH_INTENT:
             for error in results["errors"]:
                 logger.error(f"Environment check failed: {error}")
                 
        return results


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
        effective_namespace = namespace or self.namespace
        
        # Parse timestamp if provided as string
        final_timestamp = datetime.now()
        if timestamp:
            if isinstance(timestamp, str):
                try:
                    # Claude Code uses ISO format like 2026-03-01T22:44:30.610Z
                    # Replace Z with +00:00 for fromisoformat
                    iso_str = timestamp.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(iso_str)
                    # Normalize to ms precision (Claude standard)
                    final_timestamp = dt.replace(microsecond=(dt.microsecond // 1000) * 1000)
                except Exception:
                    final_timestamp = datetime.now().replace(microsecond=0)
            else:
                # Normalize provided datetime objects too
                final_timestamp = timestamp.replace(microsecond=(timestamp.microsecond // 1000) * 1000)
        else:
            # New events get rounded to ms for consistency
            now = datetime.now()
            final_timestamp = now.replace(microsecond=(now.microsecond // 1000) * 1000)

        if (self.trust_boundary == TrustBoundary.HUMAN_ONLY and 
            source == "agent" and 
            kind == KIND_DECISION):
            return MemoryDecision(
                should_persist=False,
                store_type="none",
                reason="Trust Boundary Violation"
            )

        # 2.9: Special path for manual KIND_INTERVENTION
        if kind == KIND_INTERVENTION:
            stream = DecisionStream(
                decision_id=str(uuid.uuid4()) if isinstance(context, dict) and not context.get('decision_id') else (context.get('decision_id') if isinstance(context, dict) else getattr(context, 'decision_id', str(uuid.uuid4()))),
                target=context.get('target', 'unknown') if isinstance(context, dict) else getattr(context, 'target', 'unknown'),
                title=context.get('title', content) if isinstance(context, dict) else getattr(context, 'title', content),
                rationale=context.get('rationale', content) if isinstance(context, dict) else getattr(context, 'rationale', content),
                namespace=namespace or self.namespace
            )
            stream = self.reflection_engine.lifecycle.process_intervention(stream, datetime.now())
            context = stream

        # Build and Validate event
        event = MemoryEvent(
            source=source,
            kind=kind,
            content=content,
            context=context or {},
            timestamp=final_timestamp
        )
        
        # 2.5: Prevent duplicate processing (Deep check including context, ignoring links)
        if self.episodic.find_duplicate(event, ignore_links=True).value:
            return MemoryDecision(
                should_persist=False,
                store_type="none",
                reason="Duplicate event detected"
            )

        # 2.6: Deep Conflict Detection for semantic records
        decision = self.router.route(event, intent=intent)
        if decision:
             if decision.should_persist and decision.store_type == "semantic" and not intent:
                 # Check for active conflicts that aren't being superseded
                 if conflict_msg := self.conflict_engine.check_for_conflicts(event, namespace=effective_namespace):
                     return MemoryDecision(
                         should_persist=False,
                         store_type="none",
                         reason=f"Invariant Violation: {conflict_msg}"
                     )
        
        if decision and decision.should_persist:
            if decision.store_type == "episodic":
                if source in {"user", "agent"}:
                    ev_id = self.episodic.append(event).value
                    decision.metadata["event_id"] = ev_id
                    self.events.emit("episodic_added", {"id": ev_id, "kind": event.kind})
            elif decision.store_type == "semantic":
                logger.debug("Starting semantic transaction...")
                # Use Transaction for atomic save + status updates
                with self.semantic.transaction():
                    logger.debug("Inside transaction block...")
                    # 1. Update back-links and deactivate old versions BEFORE saving new one
                    if intent and intent.resolution_type == "supersede":
                        for old_id in intent.target_decision_ids:
                            # Verify it exists and is active before deactivating
                            old_meta = self.semantic.meta.get_by_fid(old_id)
                            if old_meta and old_meta.get('status') == 'active':
                                logger.debug(f"Deactivating old decision {old_id}...")
                                self.semantic.update_decision(
                                    old_id, 
                                    {"status": "superseded"},
                                    commit_msg=f"Deactivating for transition"
                                )
                            else:
                                logger.info(f"Target {old_id} already superseded or missing during transition.")

                    # 2.7: Late-bind Conflict Detection (Inside Lock)
                    if conflict_msg := self.conflict_engine.check_for_conflicts(event, namespace=effective_namespace):
                        logger.warning(f"Race condition prevented: {conflict_msg}")
                        raise ConflictError(f"Conflict detected during transaction: {conflict_msg}")

                    # 2. Prepare context for new decision
                    if isinstance(event.context, (DecisionContent, DecisionStream, ProposalContent)):
                        if intent and intent.resolution_type == "supersede":
                            event.context.supersedes = intent.target_decision_ids
                        event.context.namespace = effective_namespace
                        if isinstance(context, dict) and 'evidence_event_ids' in context:
                            event.context.evidence_event_ids = context['evidence_event_ids']

                        # IMPORTANT: Convert Pydantic model to DICT with JSON-safe values (Enums to strings)
                        event.context = event.context.model_dump(mode='json')

                    elif isinstance(event.context, dict):
                        if intent and intent.resolution_type == "supersede":
                            event.context["supersedes"] = intent.target_decision_ids
                        event.context["namespace"] = effective_namespace
                        if isinstance(context, dict) and 'evidence_event_ids' in context:
                            event.context['evidence_event_ids'] = context['evidence_event_ids']

                    # 3. Save new decision
                    new_fid = self.semantic.save(event, namespace=effective_namespace)
                    decision.metadata["file_id"] = new_fid
                    self.events.emit("semantic_added", {"id": new_fid, "kind": event.kind, "namespace": effective_namespace})

                    # 4. Now that we have new_fid, update back-links properly
                    if intent and intent.resolution_type == "supersede":
                        for old_id in intent.target_decision_ids:
                            self.semantic.update_decision(
                                old_id, 
                                {"status": "superseded", "superseded_by": new_fid},
                                commit_msg=f"Superseded by {new_fid}"
                            )

                    # Link grounding evidence to the new semantic record
                    all_grounding_ids = set()
                    if isinstance(event.context, dict):
                        all_grounding_ids.update(event.context.get('evidence_event_ids', []))
                    elif hasattr(event.context, 'evidence_event_ids'):
                        all_grounding_ids.update(getattr(event.context, 'evidence_event_ids', []))

                    # Inherit links from superseded items
                    if intent and intent.resolution_type == "supersede":
                        # ⚡ Bolt Optimization: Batch fetch all linked events for superseded decisions
                        # This eliminates N+1 SQLite queries when superseding multiple items at once
                        try:
                            old_links_map = self.episodic.get_linked_event_ids_batch(intent.target_decision_ids)
                            for old_id in intent.target_decision_ids:
                                if old_id in old_links_map:
                                    all_grounding_ids.update(old_links_map[old_id])
                        except Exception as e:
                            # Maintain the original granularity: log the failure but don't crash
                            logger.warning(f"Failed to fetch links from superseded items {intent.target_decision_ids}: {e}")

                    if all_grounding_ids:
                        for ev_id in all_grounding_ids:
                            try:
                                self.episodic.link_to_semantic(ev_id, new_fid)
                            except Exception as le:
                                logger.warning(f"Failed to link grounding evidence {ev_id} to {new_fid}: {le}")

                logger.debug("Transaction committed. Now indexing in VectorStore...")
                if vector is not None:
                    try:
                        indexed_content = event.content
                        ctx = event.context
                        rationale_val = ""
                        if isinstance(ctx, dict):
                            rationale_val = ctx.get('rationale', '')
                        elif hasattr(ctx, 'rationale'):
                            rationale_val = getattr(ctx, 'rationale', '')

                        if rationale_val:
                            indexed_content = f"{event.content}\n{rationale_val}"

                        self.vector.add_documents([{
                            "id": new_fid,
                            "content": indexed_content
                        }], embeddings=[vector])
                    except Exception as ve:
                        logger.warning(f"Vector indexing failed for {new_fid}: {ve}")
                else:
                    logger.debug(f"Vector indexing deferred for {new_fid} (no pre-computed vector).")

                # Immortal Link (Skip for background sources to keep episodic memory clean)
                if source in {"user", "agent"}:
                    ev_id = self.episodic.append(event, linked_id=new_fid).value
                    decision.metadata["event_id"] = ev_id

        return decision

    def get_decisions(self) -> List[str]:
        """
        List all active decision identifiers in the semantic store.
        """
        return self.semantic.list_decisions()

    def get_decision_history(self, decision_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve the full version history of a specific decision from the audit log.
        """
        self.semantic._validate_fid(decision_id)
        return self.semantic.audit.get_history(decision_id)

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
        
        # Performance: Increment link_count in metadata for O(1) grounding retrieval
        with self.semantic.transaction():
            self.semantic.meta._conn.execute(
                "UPDATE semantic_meta SET link_count = link_count + 1 WHERE fid = ?",
                (semantic_id,)
            )

    def update_decision(self, decision_id: str, updates: Dict[str, Any], commit_msg: str, skip_episodic: bool = False) -> bool:
        """
        Coordinates updates to a semantic record across all stores.
        """
        self.semantic._validate_fid(decision_id)
        
        # Ensure updates are JSON-safe (Enums to strings, datetimes to ISO strings)
        def _json_safe(v):
            if hasattr(v, 'value'): # Enum
                return v.value
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, list):
                return [_json_safe(item) for item in v]
            if isinstance(v, dict):
                return {k: _json_safe(val) for k, val in v.items()}
            return v

        updates = {k: _json_safe(v) for k, v in updates.items()}

        # 0. Performance & Cleanliness Optimization: Skip if no actual changes
        current_meta = self.semantic.meta.get_by_fid(decision_id)
        if current_meta:
            has_changes = False
            import json
            current_ctx = json.loads(current_meta.get('context_json', '{}'))
            
            for key, val in updates.items():
                # Compare against metadata fields OR context fields
                current_val = current_meta.get(key)
                if current_val is None:
                    current_val = current_ctx.get(key)
                
                if current_val != val:
                    has_changes = True
                    break
            
            if not has_changes:
                logger.debug(f"Update skipped for {decision_id}: No changes detected.")
                return True

        with self.semantic.transaction():
            # 1. Update Semantic Store (Filesystem + Metadata DB)
            self.semantic.update_decision(decision_id, updates, commit_msg)
            
            # 2. Update Vector Index if content/rationale changed
            if "content" in updates or "rationale" in updates:
                meta = self.semantic.meta.get_by_fid(decision_id)
                if meta:
                    indexed_content = meta.get('content', '')
                    try:
                        self.vector.add_documents([{
                            "id": decision_id,
                            "content": indexed_content
                        }])
                    except Exception as ve:
                        logger.warning(f"Vector re-indexing failed for {decision_id}: {ve}")
            
            # 3. Create episodic event to log the update (Issue #11: Log phase changes for all)
            if not skip_episodic:
                meta = self.semantic.meta.get_by_fid(decision_id)
                if meta:
                    # Check for phase transition
                    old_phase = current_ctx.get('phase')
                    new_phase = updates.get('phase')
                    
                    if new_phase and old_phase != new_phase:
                        self.episodic.append(MemoryEvent(
                            source="system",
                            kind="commit_change",
                            content=f"Lifecycle: {old_phase} → {new_phase} for {meta.get('title')}",
                            context={
                                "target": meta.get('target'),
                                "fid": decision_id,
                                "old_phase": old_phase,
                                "new_phase": new_phase
                            }
                        ), linked_id=decision_id).value

                    if meta.get('kind') != KIND_PROPOSAL:
                        event = MemoryEvent(
                            source="system",
                            kind="commit_change",
                            content=f"Updated {meta.get('kind')}: {meta.get('title')}",
                            context={
                                "original_kind": meta.get('kind', 'decision'),
                                "updates": updates,
                                "target": meta.get('target'),
                                "rationale": commit_msg
                            }
                        )
                        if not self.episodic.find_duplicate(event, linked_id=decision_id).value:
                            self.episodic.append(event, linked_id=decision_id).value
            
        return True

    def run_decay(self, dry_run: bool = False, stop_event: Optional[threading.Event] = None) -> DecayReport:
        """
        Execute the decay process for episodic and semantic memories.
        Supports interruption via stop_event.
        """
        # 1. Episodic Decay
        all_events = self.episodic.query(limit=20000, status=None)
        to_archive, to_prune, retained = self.decay_engine.evaluate(all_events)
        
        # 2. Semantic Decay
        all_decisions = self.semantic.meta.list_all()
        semantic_results = self.decay_engine.evaluate_semantic(all_decisions)
        
        forgotten_count = 0
        if not dry_run:
            with self.semantic.transaction():
                # Apply Episodic changes
                self.episodic.mark_archived(to_archive)
                self.episodic.physical_prune(to_prune)
                
                # Apply Semantic changes
                for fid, new_conf, should_forget in semantic_results:
                    # INTERRUPT CHECK
                    if stop_event and stop_event.is_set():
                        logger.info("Decay: Interrupted by stop event.")
                        break

                    if should_forget:
                        logger.info(f"Semantic Decay: Forgetting {fid} (confidence dropped to {new_conf})")
                        self.forget(fid)
                        forgotten_count += 1
                    else:
                        updates = {"confidence": new_conf}
                        
                        # Logic for deprecating stale decisions
                        meta = self.semantic.meta.get_by_fid(fid)
                        if meta and meta.get('kind') in ('decision', 'constraint') and meta.get('status') == 'active':
                            if new_conf < 0.5:
                                logger.info(f"Semantic Decay: Deprecating {fid} (confidence dropped to {new_conf})")
                                updates["status"] = "deprecated"
                        
                        self.semantic.update_decision(fid, updates, 
                                                      commit_msg=f"Decay: Reduced confidence to {new_conf}")
            
        return DecayReport(len(to_archive), len(to_prune), retained, semantic_forgotten=forgotten_count)

    def run_reflection(self, stop_event: Optional[threading.Event] = None) -> List[str]:
        """
        Execute the incremental reflection process to identify patterns.
        Processes the entire delta of new events since the last watermark.
        """
        watermark_key = "last_reflection_event_id"
        last_id = self.semantic.meta.get_config(watermark_key)
        after_id = int(last_id) if last_id is not None else 0
        
        all_proposal_ids = []
        CHUNK_SIZE = 5000
        # Increased MAX_TOTAL to avoid infinite loops if somehow max_id doesn't advance
        MAX_TOTAL = 100000 
        processed_total = 0
        
        while processed_total < MAX_TOTAL:
            # INTERRUPT CHECK
            if stop_event and stop_event.is_set():
                logger.info("Reflection: Interrupted by stop event.")
                break

            # Process in small chunks to avoid memory spikes
            proposal_ids, new_max_id = self.reflection_engine.run_cycle(after_id=after_id, limit=CHUNK_SIZE)
            
            if new_max_id is None or new_max_id <= after_id:
                # No more events to process
                break
                
            all_proposal_ids.extend(proposal_ids)
            after_id = new_max_id
            processed_total += CHUNK_SIZE
            
            # Save watermark incrementally
            if self.semantic._fs_lock.acquire(exclusive=True, timeout=30):
                try:
                    self.semantic.meta.set_config(watermark_key, str(new_max_id))
                    logger.debug(f"Reflection: Watermark advanced to {new_max_id}")
                finally:
                    self.semantic._fs_lock.release()
            
            if len(proposal_ids) < CHUNK_SIZE / 2: # Very few results or no more new events
                 # Check if we should really break - if new_max_id advanced, there might be more
                 # But usually episodic query will return fewer than limit only at the end.
                 pass

        return all_proposal_ids

    def sync_git(self, repo_path: str = ".", limit: int = 20) -> int:
        """
        Syncs recent Git commits into episodic memory.
        """
        indexer = GitIndexer(repo_path)
        return indexer.index_to_memory(self, limit=limit)

    def record_decision(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None, evidence_ids: Optional[List[int]] = None, namespace: Optional[str] = None, arbiter_callback: Optional[callable] = None) -> MemoryDecision:
        """
        Helper to record a new decision in semantic memory.
        """
        if not title.strip(): raise ValueError("Title cannot be empty")
        if not target.strip(): raise ValueError("Target cannot be empty")
        if not rationale.strip(): raise ValueError("Rationale cannot be empty")

        effective_namespace = namespace or self.namespace
        target = self.targets.normalize(target)
        self.targets.register(target, description=title)

        active_conflicts = self.semantic.list_active_conflicts(target, namespace=effective_namespace)
        new_vec_cached = None
        
        if self.vector:
            try:
                from ledgermind.core.stores.vector import _is_transformers_available
                can_compute = _is_transformers_available() or (hasattr(self.vector, "model") and self.vector.model is not None)
                
                if can_compute:
                    import numpy as np
                    from difflib import SequenceMatcher
                    
                    new_text = f"{title}\n{rationale}"
                    new_vec = self.vector.model.encode([new_text])[0]
                    new_vec_cached = new_vec # Cache for later indexing
                    new_norm = np.linalg.norm(new_vec)
                    
                    if active_conflicts:
                        for old_fid in active_conflicts:
                            old_meta = self.semantic.meta.get_by_fid(old_fid)
                            old_vec = self.vector.get_vector(old_fid)
                            if old_vec is None or not old_meta:
                                continue
            
                            old_norm = np.linalg.norm(old_vec)
                            sim = float(np.dot(new_vec, old_vec) / (new_norm * old_norm + 1e-9))

                            logger.debug(f"Conflict Check: {old_fid} | Sim: {sim:.4f} | Arbiter: {bool(arbiter_callback)}")

                            old_title = old_meta.get('title', '')

                            title_sim = SequenceMatcher(None, title.lower(), old_title.lower()).ratio()
                            if title_sim > 0.90:
                                sim = max(sim, 0.71)
            
                            if 0.50 <= sim < 0.70 and arbiter_callback:
                                new_data = {"title": title, "rationale": rationale}
                                old_data = {"title": old_title, "rationale": old_meta.get('content', '')}
                                if arbiter_callback(new_data, old_data) == "SUPERSEDE":
                                    sim = 0.71
            
                            if sim > 0.70:
                                try:
                                    return self.supersede_decision(
                                        title=title,
                                        target=target,
                                        rationale=f"Auto-Evolution: Updated based on high similarity ({sim:.2f}). {rationale}",
                                        old_decision_ids=[old_fid],
                                        consequences=consequences,
                                        evidence_ids=evidence_ids,
                                        namespace=effective_namespace,
                                        vector=new_vec # Reuse the vector we just computed
                                    )
                                except ConflictError:
                                    # Re-raise conflict errors to avoid double reporting
                                    raise
                                except Exception as e:
                                    logger.warning(f"Auto-resolution failed for {old_fid}: {e}")
            except Exception as e:
                # Only log if it's not a missing engine error
                if "not found" not in str(e).lower() and "missing" not in str(e).lower():
                    logger.warning(f"Similarity check failed: {e}")
            
        if active_conflicts:
            suggestions = self.targets.suggest(target)
            msg = f"CONFLICT: Target '{target}' in namespace '{effective_namespace}' already has active decisions: {active_conflicts}. "
            if suggestions:
                msg += f"Did you mean: {', '.join(suggestions)}?"
            raise ConflictError(msg)

        import uuid
        ctx = DecisionStream(
            decision_id=str(uuid.uuid4()),
            title=title,
            target=target,
            rationale=rationale,
            consequences=consequences or [],
            evidence_event_ids=evidence_ids or [],
            namespace=effective_namespace
        )
        
        # Apply intervention logic to set default emergent phase and high responsibility
        ctx = self._lifecycle.process_intervention(ctx, datetime.now())

        decision = self.process_event(
            source="agent",
            kind=KIND_DECISION,
            content=title,
            context=ctx,
            namespace=effective_namespace,
            vector=new_vec_cached
        )
        if not decision.should_persist:
            if "CONFLICT" in decision.reason:
                raise ConflictError(decision.reason)
            raise InvariantViolation(f"Failed to record decision: {decision.reason}")
        return decision

    def supersede_decision(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None, evidence_ids: Optional[List[int]] = None, namespace: Optional[str] = None, vector: Optional[Any] = None) -> MemoryDecision:
        """
        Helper to evolve knowledge by superseding existing decisions.
        """
        effective_namespace = namespace or self.namespace
        
        # Verify all target IDs exist and are active BEFORE starting the process
        for oid in old_decision_ids:
            meta = self.semantic.meta.get_by_fid(oid)
            if not meta:
                raise ConflictError(f"Cannot supersede {oid}: it does not exist in the semantic store.")
            
            if meta.get('status') != 'active':
                raise ConflictError(f"Cannot supersede {oid}: it is no longer active (current status: {meta.get('status')}).")

        intent = ResolutionIntent(
            resolution_type="supersede",
            rationale=rationale,
            target_decision_ids=old_decision_ids
        )
        import uuid
        ctx = DecisionStream(
            decision_id=str(uuid.uuid4()),
            title=title,
            target=target,
            rationale=rationale,
            consequences=consequences or [],
            evidence_event_ids=evidence_ids or [],
            namespace=effective_namespace,
            phase=DecisionPhase.EMERGENT,
            vitality=DecisionVitality.ACTIVE,
            first_seen=datetime.now(),
            last_seen=datetime.now()
        )
        decision = self.process_event(
            source="agent",
            kind=KIND_DECISION,
            content=title,
            context=ctx,
            intent=intent,
            namespace=effective_namespace,
            vector=vector
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
        from ledgermind.core.stores.semantic_store.loader import MemoryLoader
        file_path = os.path.join(self.semantic.repo_path, proposal_id)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Proposal not found: {proposal_id}")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            data, _ = MemoryLoader.parse(f.read())
        
        if data.get("kind") != "proposal":
            raise ValueError(f"File {proposal_id} is not a proposal")
            
        ctx = data.get("context", {})
        current_status = str(ctx.get("status", "")).lower()
        if current_status != "draft":
            raise ValueError(f"Proposal {proposal_id} is already {current_status}")

        try:
            with self.semantic.transaction():
                supersedes = ctx.get("suggested_supersedes", [])
                target = ctx.get("target")
                title = ctx.get("title")
                enrichment_status = ctx.get("enrichment_status")
                final_rationale = ctx.get("rationale", "")

                # --- RATIONALE SYNTHESIS FOR MERGES ---
                # If LLM enrichment is already completed, we MUST use the synthesized rationale 
                # from the proposal itself instead of re-synthesizing it from scratch (Issue #15)
                if target == "knowledge_merge" and supersedes:
                    if enrichment_status != "completed":
                        original_rationales = []
                        for sid in supersedes:
                            try:
                                s_data = self.semantic.get_decision(sid)
                                if s_data and s_data.rationale:
                                    original_rationales.append(s_data.rationale)
                            except Exception: continue
                        
                        if original_rationales:
                            from ledgermind.core.reasoning.llm_enrichment import LLMEnricher
                            # Use optimal/rich mode if available for merge synthesis
                            mode = self.semantic.meta.get_config("arbitration_mode", "lite")
                            enricher = LLMEnricher(mode=mode)
                            final_rationale = enricher.synthesize_merged_rationale(original_rationales)
                    else:
                        logger.info(f"Using pre-enriched rationale for merge proposal {proposal_id}")
                        # Keep the existing final_rationale which was loaded from ctx['rationale']
                else:
                    if enrichment_status != "completed":
                        final_rationale = f"Accepted proposal {proposal_id}. {final_rationale}"

                grounding_ids = set(ctx.get("evidence_event_ids", []))
                
                # --- EVIDENCE INHERITANCE ---
                # Automatically collect all evidence IDs from the decisions being superseded
                if supersedes:
                    for sid in supersedes:
                        try:
                            old_data = self.semantic.meta.get_by_fid(sid)
                            if old_data and old_data.get('context_json'):
                                import json
                                old_ctx = json.loads(old_data['context_json'])
                                grounding_ids.update(old_ctx.get('evidence_event_ids', []))
                        except Exception as e:
                            logger.warning(f"Failed to inherit evidence from {sid}: {e}")

                try:
                    grounding_ids.update(self.episodic.get_linked_event_ids(proposal_id))
                except Exception: pass
                evidence_ids = list(grounding_ids)
                
                if supersedes:
                    decision = self.supersede_decision(
                        title=title,
                        target=target,
                        rationale=final_rationale,
                        old_decision_ids=supersedes,
                        consequences=ctx.get("suggested_consequences", []),
                        evidence_ids=evidence_ids
                    )
                else:
                    decision = self.record_decision(
                        title=title,
                        target=target,
                        rationale=final_rationale,
                        consequences=ctx.get("suggested_consequences", []),
                        evidence_ids=evidence_ids
                    )
                
                if decision.should_persist:
                    new_id = decision.metadata.get("file_id")
                    self.semantic.update_decision(
                        proposal_id, 
                        {"status": "accepted", "converted_to": new_id}, 
                        commit_msg=f"Accepted and converted to {new_id}"
                    )
        except Exception as e:
            # Explicitly rollback proposal to draft (Issue #9)
            # This is now OUTSIDE the transaction above, so it will persist even if the transaction failed.
            logger.warning(f"Proposal conversion failed: {e}. Ensuring status remains 'draft'.")
            try:
                self.semantic.update_decision(proposal_id, {"status": "draft"}, f"Conversion failed: {str(e)}")
            except Exception as ue:
                logger.error(f"Critical: Failed to reset proposal status to draft: {ue}")
            raise
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

    def search_decisions(self, query: str, limit: int = 5, offset: int = 0, namespace: Optional[str] = None, mode: str = "balanced") -> List[Dict[str, Any]]:
        """
        Search with Recursive Truth Resolution and Hybrid Vector/Keyword ranking (RRF).
        Now supports namespacing, pagination, and history filtering.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            offset: Number of results to skip (for pagination)
            namespace: Namespace to search in (default: self.namespace)
            mode: Search mode - "strict" (active only), "balanced" (with history)
                    See `include_history` for actual behavior control.

        Excluded from search (technical statuses):
            - "processed": Merge trigger proposals (not real knowledge)
            - "knowledge_merge": Merge trigger proposals (not real knowledge)
            - "knowledge_validation": Validation trigger proposals (not real knowledge)
            - "accepted": Merged/accepted proposals (superseded by real decision)
        """
        effective_namespace = namespace or self.namespace
        k = 60 # RRF constant
        
        # Fast path for simple keyword search in high-performance scenarios
        if mode == "lite" or (len(query) < 20 and " " not in query.strip()):
            search_status = "active" if mode == "strict" else None
            kw_results = self.semantic.meta.keyword_search(query, limit=limit, namespace=effective_namespace, status=search_status)
            if kw_results:
                # Absolute maximum throughput by minimizing dict keys and using direct index access
                return [{
                    "id": r[0],
                    "title": r[1],
                    "preview": r[1],
                    "target": r[2],
                    "status": r[3],
                    "score": 1.0,
                    "kind": r[4]
                } for r in kw_results]

        if namespace:
            search_limit = max(200, (offset + limit) * 10)
        else:
            search_limit = (offset + limit) * 3
        
        vec_results = []
        try:
            vec_results = self.vector.search(query, limit=search_limit)
        except Exception: pass
            
        kw_results = self.semantic.meta.keyword_search(query, limit=search_limit, namespace=effective_namespace)
        
        # Batch Fetch Metadata for all results at once to avoid N+1 in score loops
        all_initial_fids = list(set([item['id'] for item in vec_results] + [r[0] for r in kw_results]))
        meta_cache = {m['fid']: m for m in self.semantic.meta.get_batch_by_fids(all_initial_fids)}

        scores = {}
        for rank, item in enumerate(vec_results):
            fid = item['id']
            meta = meta_cache.get(fid)
            weight = 1.0
            if meta:
                if meta.get('kind') == 'decision':
                    weight *= 1.35
                phase = (meta.get('phase') or '').lower()
                if phase == 'canonical':
                    weight *= 1.5
                elif phase == 'emergent':
                    weight *= 1.2
            
            scores[fid] = scores.get(fid, 0.0) + (weight / (k + rank + 1))
            
        for rank, r in enumerate(kw_results):
            fid = r[0]
            meta = meta_cache.get(fid)
            weight = 1.0
            if meta:
                if meta.get('kind') == 'decision':
                    weight *= 1.35
                phase = (meta.get('phase') or '').lower()
                if phase == 'canonical':
                    weight *= 1.5
                elif phase == 'emergent':
                    weight *= 1.2
            
            scores[fid] = scores.get(fid, 0.0) + (weight / (k + rank + 1))

        max_rrf = 3.0 / (k + 1.0) # Theoretical max boost
        sorted_fids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        # Batch Fetch Optimization (PR #25)
        candidates_meta = self.semantic.meta.get_batch_by_fids(sorted_fids)
        request_cache = {m['fid']: m for m in candidates_meta}

        current_layer_ids = [m['superseded_by'] for m in candidates_meta if m.get('superseded_by')]
        current_layer_ids = [fid for fid in current_layer_ids if fid and fid not in request_cache]

        iteration = 0
        while current_layer_ids and iteration < 5:
            new_batch = self.semantic.meta.get_batch_by_fids(current_layer_ids)
            for m in new_batch:
                request_cache[m['fid']] = m
            current_layer_ids = [m['superseded_by'] for m in new_batch if m.get('superseded_by')]
            current_layer_ids = [fid for fid in current_layer_ids if fid and fid not in request_cache]
            iteration += 1
        
        if current_layer_ids:
            logger.warning(f"Deep supersession chain detected (>5 levels). Falling back to CTE for {len(current_layer_ids)} records.")

        # Gather all resolved truth records to batch query links
        resolved_records = []
        for fid in sorted_fids:
            meta = self._resolve_to_truth(fid, mode, cache=request_cache)
            if not meta: continue
            
            if meta.get('namespace', 'default') != effective_namespace:
                continue

            status = meta.get("status", "unknown")

            # Technical statuses that should not appear in search results
            TECHNICAL_STATUSES = ("processed", "knowledge_merge", "knowledge_validation", "accepted")
            if status in TECHNICAL_STATUSES:
                continue

            # Filter based on history mode
            # Whitelist pending_merge so it stays visible during consolidation
            if not self.include_history and status not in ("active", "superseded", "deprecated", "pending_merge"):
                continue
            if mode == "strict" and status not in ("active", "pending_merge"):
                continue

            resolved_records.append((fid, meta, scores[fid] / max_rrf))

        # Batch Fetch Links (N+1 Query Optimization)
        unique_final_ids = list(set([r[1]['fid'] for r in resolved_records]))
        link_counts = self.episodic.count_links_for_semantic_batch(unique_final_ids)

        # Aggregate scores for identical truth records (RRF Aggregation)
        final_candidates = {}
        for fid, meta, match_score in resolved_records:
            final_id = meta['fid']
            status = meta.get("status", "unknown")

            if final_id in final_candidates:
                # Accumulate score contribution from this historical/related match
                final_candidates[final_id]['base_score'] += match_score
                continue

            link_count = link_counts.get(final_id, (0, 0.0))[0]
            boost = min(link_count * 0.2, 1.0) 
            
            # Dynamic Lifecycle Multiplier (Balanced Model)
            phase = meta.get('phase', 'pattern').lower()
            vitality = meta.get('vitality', 'active').lower()
            kind = meta.get('kind', 'proposal').lower()
            
            phase_weights = {"canonical": 1.5, "emergent": 1.2, "pattern": 1.0}
            vitality_weights = {"active": 1.0, "decaying": 0.5, "dormant": 0.2}
            kind_weights = {"decision": 1.35, "proposal": 1.0} # Decision gets ~35% boost
            
            lifecycle_multiplier = (
                phase_weights.get(phase, 1.0) * 
                vitality_weights.get(vitality, 1.0) * 
                kind_weights.get(kind, 1.0)
            )
            
            if status in ("rejected", "falsified"): lifecycle_multiplier *= 0.2
            elif status in ("superseded", "deprecated"): lifecycle_multiplier *= 0.3
            
            final_candidates[final_id] = {
                "id": final_id,
                "base_score": match_score,
                "boost": boost,
                "lifecycle_multiplier": lifecycle_multiplier,
                "status": status,
                "title": meta.get("title", "unknown"),
                "preview": meta.get("title", "unknown"),
                "target": meta.get("target", "unknown"),
                "content": meta.get("content", ""),
                "context_json": meta.get('context_json', '{}'),
                "kind": meta.get("kind"),
                "is_active": (status == "active"),
                "evidence_count": link_count,
                "vitality": vitality,
                "phase": phase
            }

        all_candidates = []
        for cand in final_candidates.values():
            # Apply multipliers to the aggregated base score + evidence boost
            # We use addition for boosts and multipliers for lifecycle focus
            # Final score is clipped to [0, 1] range for threshold consistency
            raw_score = (cand['base_score'] + cand['boost']) * cand['lifecycle_multiplier']
            cand['score'] = min(1.0, raw_score)
            all_candidates.append(cand)

        all_candidates.sort(key=lambda x: x['score'], reverse=True)
        final_results = []
        seen_ids = set()
        skipped = 0
        
        for cand in all_candidates:
            if cand['id'] in seen_ids: continue
            if skipped < offset:
                skipped += 1
                continue
            
            try:
                ctx = json.loads(cand.pop('context_json'))
            except Exception:
                ctx = {}
            cand["rationale"] = ctx.get("rationale")
            cand["consequences"] = ctx.get("consequences")
            cand["expected_outcome"] = ctx.get("expected_outcome")
                
            final_results.append(cand)
            seen_ids.add(cand['id'])
            try:
                self.semantic.meta.increment_hit(cand['id'])
            except Exception: pass
            
            if len(final_results) >= limit: break
            
        return final_results

    def _resolve_to_truth(self, doc_id: str, mode: str, cache: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """Recursively follows 'superseded_by' links using Metadata Store."""
        self.semantic._validate_fid(doc_id)

        if mode == "audit":
            if cache and doc_id in cache: return cache[doc_id]
            return self.semantic.meta.get_by_fid(doc_id)

        # Optimization: Use cache first if available (PR #25)
        if cache:
            current_id = doc_id
            depth = 0
            while depth < 20:
                if current_id in cache:
                    meta = cache[current_id]
                    status = meta.get("status")
                    successor = meta.get("superseded_by")
                    if status == "active" or not successor:
                        return meta
                    current_id = successor
                    depth += 1
                else:
                    # Fallback to CTE if cache miss
                    break
            else:
                return None

        # Fallback to CTE query (origin/main)
        return self.semantic.meta.resolve_to_truth(doc_id)

    def generate_knowledge_graph(self, target: Optional[str] = None) -> str:
        """Generates a Mermaid graph of knowledge evolution."""
        from ledgermind.core.reasoning.ranking.graph import KnowledgeGraphGenerator
        generator = KnowledgeGraphGenerator(self.semantic.repo_path, self.semantic.meta, self.episodic)
        return generator.generate_mermaid(target_filter=target)

    def run_maintenance(self, stop_event: Optional[threading.Event] = None) -> Dict[str, Any]:
        """Runs periodic maintenance tasks. Supports interruption via stop_event."""
        from ledgermind.core.stores.semantic_store.integrity import IntegrityChecker
        self.semantic.sync_meta_index()
        integrity_status = "ok"
        try:
            IntegrityChecker.validate(self.semantic.repo_path, force=True)
        except Exception as ie:
            logger.error(f"Integrity Violation: {ie}")
            integrity_status = f"violation: {str(ie)}"

        if stop_event and stop_event.is_set(): return {"integrity": integrity_status}

        # 0. Lifecycle Update (Phase transitions & Vitality decay)
        reflection_proposals = self.run_reflection(stop_event=stop_event)
        
        if stop_event and stop_event.is_set(): 
            return {"integrity": integrity_status, "reflection": {"proposals_created": len(reflection_proposals)}}

        decay_report = self.run_decay(stop_event=stop_event)
        
        # Update metrics (Issue #16)
        stats = self.get_stats()
        if VITALITY_DISTRIBUTION:
            for v, count in stats.get('vitality', {}).items():
                VITALITY_DISTRIBUTION.labels(vitality=v).set(count)
        if PHASE_DISTRIBUTION:
            for p, count in stats.get('phases', {}).items():
                PHASE_DISTRIBUTION.labels(phase=p).set(count)

        if stop_event and stop_event.is_set(): 
            return {"integrity": integrity_status, "decay": decay_report.__dict__}

        from ledgermind.core.reasoning.merging import MergeEngine
        
        # --- VECTOR SYNC (Auto-reindexing missing entries) ---
        self.reindex_missing(stop_event=stop_event)

        if stop_event and stop_event.is_set(): 
            return {"integrity": integrity_status, "decay": decay_report.__dict__}

        merger = MergeEngine(self)
        merges = merger.scan_for_duplicates()

        return {
            "decay": decay_report.__dict__,
            "reflection": {"proposals_created": len(reflection_proposals)},
            "merging": {"proposals_created": len(merges), "ids": merges},
            "integrity": integrity_status
        }

    def reindex_missing(self, limit: int = 50, stop_event: Optional[threading.Event] = None):
        """
        Identifies active decisions missing from the vector index and re-indexes them.
        """
        if not self.vector: return
        
        try:
            # 1. Get all active & enriched FIDs from Meta
            all_metas = self.semantic.meta.list_all()
            active_metas = [m for m in all_metas if m.get('status') == 'active']
            
            if not active_metas: return
            
            # 2. Get all IDs currently in Vector Store
            indexed_ids = set(self.vector.get_all_ids())
            
            # 3. Find delta
            missing = [m for m in active_metas if m['fid'] not in indexed_ids]
            
            if not missing:
                return
                
            logger.info(f"Re-indexing {len(missing)} missing entries in vector store...")
            
            # 4. Batch Process
            docs_to_add = []
            for m in missing[:limit]:
                # INTERRUPT CHECK
                if stop_event and stop_event.is_set(): break

                try:
                    # Construct content for indexing (Title + Rationale)
                    import json
                    ctx = json.loads(m.get('context_json', '{}'))
                    rationale = ctx.get('rationale', '') or m.get('content', '')
                    
                    indexed_text = f"{m.get('title', '')}\n{rationale}"
                    docs_to_add.append({
                        "id": m['fid'],
                        "content": indexed_text,
                        "metadata": {"target": m.get('target'), "kind": m.get('kind')}
                    })
                except Exception as e:
                    logger.warning(f"Failed to prepare {m['fid']} for re-indexing: {e}")
            
            if docs_to_add:
                # We use None for embeddings to force VectorStore to compute them using its internal model
                self.vector.add_documents(docs_to_add, stop_event=stop_event)
                self.vector.save()
                logger.info(f"Successfully re-indexed {len(docs_to_add)} documents.")
                
        except Exception as e:
            logger.error(f"Auto-reindexing failed: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Returns diagnostic statistics including lifecycle distribution."""
        all_meta = self.semantic.meta.list_all()
        
        phases = {}
        vitality = {}
        for m in all_meta:
            p = m.get('phase', 'pattern')
            phases[p] = phases.get(p, 0) + 1
            v = m.get('vitality', 'active')
            vitality[v] = vitality.get(v, 0) + 1

        return {
            "semantic_total": len(all_meta),
            "phases": phases,
            "vitality": vitality,
            "namespace": self.namespace,
            "storage_path": self.storage_path
        }

    def forget(self, decision_id: str):
        """Hard-deletes a memory."""
        self.semantic._validate_fid(decision_id)
        self.episodic.unlink_all_for_semantic(decision_id)
        self.semantic.purge_memory(decision_id)
        self.vector.remove_id(decision_id)
        logger.info(f"Memory {decision_id} forgotten.")

    def close(self):
        """Releases all resources."""
        if hasattr(self, 'vector'): self.vector.close()
        if hasattr(self, 'semantic') and hasattr(self.semantic, 'meta'): self.semantic.meta.close()
        logger.info("Memory system closed.")
