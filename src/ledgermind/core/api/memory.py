import os
import yaml
import logging
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple

logger = logging.getLogger(__name__)

from ledgermind.core.core.router import MemoryRouter
from ledgermind.core.core.schemas import (
    MemoryEvent, MemoryDecision, ResolutionIntent, TrustBoundary, 
    DecisionContent, SEMANTIC_KINDS, KIND_DECISION, KIND_PROPOSAL,
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
from ledgermind.core.reasoning.git_indexer import GitIndexer
from ledgermind.core.stores.vector import VectorStore
from ledgermind.core.core.targets import TargetRegistry

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
                 vector_workers: Optional[int] = None):
        """
        Initialize the memory system.
        """
        if config:
            self.config = config
        else:
            self.config = LedgermindConfig(
                storage_path=storage_path or "./memory",
                ttl_days=ttl_days or 30,
                trust_boundary=trust_boundary or TrustBoundary.AGENT_WITH_INTENT,
                namespace=namespace or "default",
                vector_model=vector_model or "all-MiniLM-L6-v2",
                vector_workers=vector_workers if vector_workers is not None else 0
            )

        self.storage_path = os.path.abspath(self.config.storage_path)
        self.trust_boundary = self.config.trust_boundary
        self.namespace = self.config.namespace
        
        try:
            if not os.path.exists(self.storage_path):
                os.makedirs(self.storage_path, exist_ok=True)
        except PermissionError:
            raise ValueError(f"No permission to create storage path: {self.storage_path}")
            
        # Pluggable Storage Logic
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

        self.vector = VectorStore(
            os.path.join(self.storage_path, "vector_index"),
            model_name=self.config.vector_model,
            workers=self.config.vector_workers
        )
        self.vector.load()

        self.conflict_engine = ConflictEngine(self.semantic.repo_path, meta_store=self.semantic.meta)
        self.resolution_engine = ResolutionEngine(self.semantic.repo_path)
        self.decay_engine = DecayEngine(ttl_days=self.config.ttl_days)
        self.reflection_engine = ReflectionEngine(self.episodic, self.semantic, processor=self)
        
        self.router = MemoryRouter(
            self.conflict_engine, 
            self.resolution_engine
        )
        
        self.targets = TargetRegistry(self.semantic.repo_path)
        
        # Immediate environment check
        self.check_environment()

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
        lock_path = os.path.join(self.semantic.repo_path, ".lock")
        if os.path.exists(lock_path):
            results["storage_locked"] = True
            try:
                with open(lock_path, 'r') as f:
                    results["lock_owner"] = f.read().strip()
            except Exception:
                pass
            results["warnings"].append(f"Storage is currently locked by PID: {results['lock_owner'] or 'unknown'}")

        # 0.1 Check Vector Search (Optional)
        logger.debug("Checking vector search availability...")
        from ledgermind.core.stores.vector import EMBEDDING_AVAILABLE
        results["vector_available"] = EMBEDDING_AVAILABLE
        if not EMBEDDING_AVAILABLE:
            results["warnings"].append("Sentence-transformers not installed. Vector search is disabled.")

        # 1. Check Git
        if Memory._git_available is None:
            try:
                subprocess.run(["git", "--version"], capture_output=True, check=True)
                Memory._git_available = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                Memory._git_available = False
        
        results["git_available"] = Memory._git_available
        if not results["git_available"]:
            results["errors"].append("Git is not installed or not in PATH. Semantic storage will fail.")
        else:
            # Check git config
            try:
                name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
                email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
                if name and email:
                    results["git_configured"] = True
                else:
                    results["warnings"].append("Git user.name or user.email not configured. Commits will use defaults.")
            except Exception:
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
            context=context or {},
            parent_event_id=context.get('parent_event_id') if isinstance(context, dict) else getattr(context, 'parent_event_id', None)
        )
        
        # 2.5: Prevent duplicate processing
        if self.episodic.find_duplicate(event):
            return MemoryDecision(
                should_persist=False,
                store_type="none",
                reason="Duplicate event detected"
            )

        # 2.6: Deep Conflict Detection for semantic records
        if decision := self.router.route(event, intent=intent):
             if decision.should_persist and decision.store_type == "semantic" and not intent:
                 # Check for active conflicts that aren't being superseded
                 if conflict_msg := self.conflict_engine.check_for_conflicts(event):
                     return MemoryDecision(
                         should_persist=False,
                         store_type="none",
                         reason=f"Invariant Violation: {conflict_msg}"
                     )
        
        if decision.should_persist:
            if decision.store_type == "episodic":
                ev_id = self.episodic.append(event)
                decision.metadata["event_id"] = ev_id
            elif decision.store_type == "semantic":
                # Use Transaction for atomic save + status updates
                with self.semantic.transaction():
                    # 2.7: Late-bind Conflict Detection (Inside Lock)
                    # This prevents race conditions where two agents check simultaneously
                    if not intent:
                        if conflict_msg := self.conflict_engine.check_for_conflicts(event):
                            logger.warning(f"Race condition prevented: {conflict_msg}")
                            raise ConflictError(f"Conflict detected during transaction: {conflict_msg}")

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
                        # Combine content with rationale for better grounded search
                        indexed_content = event.content
                        ctx = event.context
                        rationale = ""
                        if isinstance(ctx, dict):
                            rationale = ctx.get('rationale', '')
                        elif hasattr(ctx, 'rationale'):
                            rationale = getattr(ctx, 'rationale', '')
                        
                        if rationale:
                            indexed_content = f"{event.content}\n{rationale}"

                        self.vector.add_documents([{
                            "id": new_fid,
                            "content": indexed_content
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
                ev_id = self.episodic.append(event, linked_id=new_fid)
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

    def update_decision(self, decision_id: str, updates: Dict[str, Any], commit_msg: str) -> bool:
        """
        Coordinates updates to a semantic record across all stores.
        """
        self.semantic._validate_fid(decision_id)
        
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
        
        # 3. Create episodic event to log the update
        meta = self.semantic.meta.get_by_fid(decision_id)
        if meta:
            event = MemoryEvent(
                source="system",
                kind=meta.get('kind', 'decision'),
                content=f"Updated {meta.get('kind')}: {meta.get('title')}",
                context={
                    "updates": updates,
                    "target": meta.get('target'),
                    "rationale": commit_msg
                }
            )
            self.episodic.append(event, linked_id=decision_id)
            
        return True

    def run_decay(self, dry_run: bool = False) -> DecayReport:
        """
        Execute the decay process for episodic and semantic memories.
        """
        # 1. Episodic Decay
        all_events = self.episodic.query(limit=20000, status=None)
        to_archive, to_prune, retained = self.decay_engine.evaluate(all_events)
        
        # 2. Semantic Decay
        all_decisions = self.semantic.meta.list_all()
        semantic_results = self.decay_engine.evaluate_semantic(all_decisions)
        
        forgotten_count = 0
        if not dry_run:
            # Apply Episodic changes
            self.episodic.mark_archived(to_archive)
            self.episodic.physical_prune(to_prune)
            
            # Apply Semantic changes
            for fid, new_conf, should_forget in semantic_results:
                if should_forget:
                    logger.info(f"Semantic Decay: Forgetting {fid} (confidence dropped to {new_conf})")
                    self.forget(fid)
                    forgotten_count += 1
                else:
                    updates = {"confidence": new_conf}
                    
                    # Logic for deprecating stale decisions
                    # Retrieve current metadata to check kind and status
                    meta = self.semantic.meta.get_by_fid(fid)
                    if meta and meta.get('kind') in ('decision', 'constraint') and meta.get('status') == 'active':
                        if new_conf < 0.5:
                            logger.info(f"Semantic Decay: Deprecating {fid} (confidence dropped to {new_conf})")
                            updates["status"] = "deprecated"
                    
                    self.semantic.update_decision(fid, updates, 
                                                  commit_msg=f"Decay: Reduced confidence to {new_conf}")
            
        return DecayReport(len(to_archive), len(to_prune), retained, semantic_forgotten=forgotten_count)

    def run_reflection(self) -> List[str]:
        """
        Execute the incremental reflection process to identify patterns.
        Uses a watermark stored in MetaStore to avoid double-processing.
        """
        # 1. Retrieve the last processed event ID
        watermark_key = "last_reflection_event_id"
        last_id = self.semantic.meta.get_config(watermark_key)
        after_id = int(last_id) if last_id is not None else None
        
        # 2. Run incremental cycle
        proposal_ids, new_max_id = self.reflection_engine.run_cycle(after_id=after_id)
        
        # 3. Update watermark if we processed new events
        if new_max_id is not None and (after_id is None or new_max_id > after_id):
            # Protect with FS lock to be safe
            if self.semantic._fs_lock.acquire(exclusive=True, timeout=5):
                try:
                    self.semantic.meta.set_config(watermark_key, new_max_id)
                    logger.info(f"Reflection: Updated watermark to {new_max_id}")
                finally:
                    self.semantic._fs_lock.release()
                
        return proposal_ids

    def sync_git(self, repo_path: str = ".", limit: int = 20) -> int:
        """
        Syncs recent Git commits into episodic memory.
        """
        indexer = GitIndexer(repo_path)
        return indexer.index_to_memory(self, limit=limit)

    def record_decision(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> MemoryDecision:
        """
        Helper to record a new decision in semantic memory.
        Automatically resolves conflicts if content similarity > 0.85 (Knowledge Evolution).
        """
        if not title.strip(): raise ValueError("Title cannot be empty")
        if not target.strip(): raise ValueError("Target cannot be empty")
        if not rationale.strip(): raise ValueError("Rationale cannot be empty")

        # 1. Target Normalization
        target = self.targets.normalize(target)
        self.targets.register(target, description=title)

        # 2. Pre-flight Conflict Check & Auto-Resolution
        active_conflicts = self.semantic.list_active_conflicts(target)
        if active_conflicts:
            # Intelligent Conflict Resolution
            try:
                from ledgermind.core.stores.vector import EMBEDDING_AVAILABLE
                if EMBEDDING_AVAILABLE and self.vector._vectors is not None:
                    import numpy as np
                    
                    # Calculate new vector
                    new_text = f"{title}\n{rationale}"
                    new_vec = self.vector.model.encode([new_text])[0]
                    new_norm = np.linalg.norm(new_vec)
                    
                    for old_fid in active_conflicts:
                        old_vec = self.vector.get_vector(old_fid)
                        if old_vec is not None:
                            old_norm = np.linalg.norm(old_vec)
                            sim = np.dot(new_vec, old_vec) / (new_norm * old_norm + 1e-9)
                            
                            if sim > 0.85:
                                logger.info(f"Auto-resolving conflict for {target} (similarity {sim:.2f}) -> Superseding {old_fid}")
                                return self.supersede_decision(
                                    title=title,
                                    target=target,
                                    rationale=f"Auto-Evolution: Updated based on high similarity ({sim:.2f}). {rationale}",
                                    old_decision_ids=[old_fid],
                                    consequences=consequences
                                )
            except Exception as e:
                logger.warning(f"Auto-resolution failed: {e}")
            
            # If we fall through, it's a hard conflict
            suggestions = self.targets.suggest(target)
            msg = f"CONFLICT: Target '{target}' already has active decisions: {active_conflicts}. "
            if suggestions:
                msg += f"Did you mean: {', '.join(suggestions)}?"
            raise ConflictError(msg)

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
        from ledgermind.core.stores.semantic_store.loader import MemoryLoader
        
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
            supersedes = ctx.get("suggested_supersedes", [])
            
            if supersedes:
                decision = self.supersede_decision(
                    title=ctx.get("title"),
                    target=ctx.get("target"),
                    rationale=f"Accepted proposal {proposal_id}. {ctx.get('rationale', '')}",
                    old_decision_ids=supersedes,
                    consequences=ctx.get("suggested_consequences", [])
                )
            else:
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
        Search with Recursive Truth Resolution and Hybrid Vector/Keyword ranking (RRF).
        Uses Metadata Cache to avoid N+1 file reads.
        """
        # 1. Execute Searches
        k = 60 # RRF constant
        search_limit = limit * 3
        
        # Vector Search
        vec_results = []
        try:
            vec_results = self.vector.search(query, limit=search_limit)
        except Exception: pass
            
        # Keyword Search (FTS)
        kw_results = self.semantic.meta.keyword_search(query, limit=limit * 10)
        
        # 2. RRF Fusion
        scores = {}
        
        for rank, item in enumerate(vec_results):
            fid = item['id']
            scores[fid] = scores.get(fid, 0.0) + (1.0 / (k + rank + 1))
            
        for rank, item in enumerate(kw_results):
            fid = item['fid']
            scores[fid] = scores.get(fid, 0.0) + (1.0 / (k + rank + 1))

        # 3. Normalization (to bring RRF into 0-1 range roughly equivalent to similarity)
        # Theoretical max RRF with 2 sources at rank 0 is 2.0 / (k + 1.0)
        max_rrf = 2.0 / (k + 1.0)

        # Sort by score descending
        sorted_fids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        candidates = []
        seen_final_ids = set()
        
        for fid in sorted_fids:
            # Resolve to truth (handle superseding)
            meta = self._resolve_to_truth(fid, mode)
            if not meta: continue
            
            final_id = meta['fid']
            if final_id in seen_final_ids: continue
            
            status = meta.get("status", "unknown")
            if mode == "strict" and status != "active": continue
            
            # Evidence boost
            link_count, _ = self.episodic.count_links_for_semantic(final_id)
            boost = min(1.0, link_count * 0.1) # +10% per link
            
            # Normalize and apply boost
            final_score = (scores[fid] / max_rrf) * (1.0 + boost)
            
            candidates.append({
                "id": final_id,
                "score": final_score,
                "status": status,
                "title": meta.get("title", "unknown"),
                "target": meta.get("target", "unknown"),
                "preview": meta.get("content", "")[:200],
                "kind": meta.get("kind"),
                "is_active": (status == "active"),
                "evidence_count": link_count
            })
            seen_final_ids.add(final_id)
            self.semantic.meta.increment_hit(final_id)
            
            if len(candidates) >= limit: break
            
        return candidates


    def _resolve_to_truth(self, doc_id: str, mode: str) -> Optional[Dict[str, Any]]:
        """Recursively follows 'superseded_by' links using Metadata Store."""
        self.semantic._validate_fid(doc_id)
        current_id = doc_id
        depth = 0
        while depth < 5:
            meta = self.semantic.meta.get_by_fid(current_id)
            if not meta: return None
            
            status = meta.get("status")
            successor = meta.get("superseded_by")
            
            if mode == "audit" or status == "active" or not successor:
                return meta
                
            current_id = successor
            depth += 1
        return None

    def generate_knowledge_graph(self, target: Optional[str] = None) -> str:
        """Generates a Mermaid graph of knowledge evolution."""
        from ledgermind.core.reasoning.ranking.graph import KnowledgeGraphGenerator
        generator = KnowledgeGraphGenerator(self.semantic.repo_path, self.semantic.meta, self.episodic)
        return generator.generate_mermaid(target_filter=target)

    def run_maintenance(self) -> Dict[str, Any]:
        """Runs periodic maintenance tasks: decay and merge analysis."""
        # 0. Deep Integrity Sync & Check
        from ledgermind.core.stores.semantic_store.integrity import IntegrityChecker
        self.semantic.sync_meta_index()
        integrity_status = "ok"
        try:
            IntegrityChecker.validate(self.semantic.repo_path, force=True)
        except Exception as ie:
            logger.error(f"Integrity Violation detected during maintenance: {ie}")
            integrity_status = f"violation: {str(ie)}"

        decay_report = self.run_decay()
        from ledgermind.core.reasoning.merging import MergeEngine
        merger = MergeEngine(self)
        merges = merger.scan_for_duplicates()
        return {
            "decay": decay_report.__dict__,
            "merging": {"proposals_created": len(merges), "ids": merges},
            "integrity": integrity_status
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
        self.vector.remove_id(decision_id)
        logger.info(f"Memory {decision_id} forgotten across systems.")

    def close(self):
        """Releases all resources held by the memory system."""
        if hasattr(self, 'vector'):
            self.vector.close()
        logger.info("Memory system closed.")

