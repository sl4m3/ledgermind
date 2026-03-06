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
            
        # 1. Initialize Storage
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

        db_model = self.semantic.meta.get_config("vector_model")
        if db_model: self.config.vector_model = db_model

        # 2. Initialize Vector Engine
        self.vector = VectorStore(
            os.path.join(self.storage_path, "vector_index"),
            model_name=self.config.vector_model,
            workers=self.config.vector_workers
        )

        self.conflict_engine = ConflictEngine(self.semantic.repo_path, meta_store=self.semantic.meta)
        self.resolution_engine = ResolutionEngine(self.semantic.repo_path)
        self.decay_engine = DecayEngine(ttl_days=self.config.ttl_days)
        self.reflection_engine = ReflectionEngine(self.episodic, self.semantic, processor=self)
        self.router = MemoryRouter(self.conflict_engine, self.resolution_engine)
        self.targets = TargetRegistry(self.semantic.repo_path)
        self._lifecycle = LifecycleEngine()

    @property
    def events(self):
        if self._events is None:
            from ledgermind.core.utils.events import EventEmitter
            self._events = EventEmitter()
        return self._events

    def check_environment(self) -> Dict[str, Any]:
        """Performs a pre-flight check of the environment."""
        results = {
            "git_available": False, "git_configured": False, "storage_writable": False,
            "disk_space_ok": False, "repo_healthy": False, "vector_available": False,
            "storage_locked": False, "lock_owner": None, "errors": [], "warnings": []
        }
        
        results["storage_locked"] = False
        try:
            if not self.semantic._fs_lock.acquire(exclusive=False, timeout=0):
                results["storage_locked"] = True
                try:
                    with open(self.semantic.lock_file, 'r') as f: results["lock_owner"] = f.read().strip()
                except Exception: pass
                results["warnings"].append(f"Storage is currently locked by PID: {results['lock_owner'] or 'unknown'}")
            else: self.semantic._fs_lock.release()
        except Exception as e: logger.debug(f"Lock check failed: {e}")

        # Vector Engine Check
        from ledgermind.core.stores.vector import _is_transformers_available, _is_llama_available, EMBEDDING_AVAILABLE, LLAMA_AVAILABLE
        is_gguf = self.config.vector_model.endswith(".gguf")
        if is_gguf:
            llama_avail = LLAMA_AVAILABLE if LLAMA_AVAILABLE is not None else _is_llama_available()
            results["vector_available"] = llama_avail
        else:
            trans_avail = EMBEDDING_AVAILABLE if EMBEDDING_AVAILABLE is not None else _is_transformers_available()
            results["vector_available"] = trans_avail

        # Git Check
        if Memory._git_available is None:
            try:
                subprocess.run(["git", "--version"], capture_output=True, check=True)
                Memory._git_available = True
            except Exception: Memory._git_available = False
        results["git_available"] = Memory._git_available
        
        # Storage check
        if os.path.exists(self.storage_path) and os.access(self.storage_path, os.W_OK):
            results["storage_writable"] = True
            try:
                if (shutil.disk_usage(self.storage_path).free / (1024*1024)) > 50: results["disk_space_ok"] = True
            except Exception: results["disk_space_ok"] = True
        return results

    def process_event(self, source: str, kind: str, content: str, 
                      context: Optional[Union[DecisionContent, DecisionStream, Dict[str, Any]]] = None,
                      intent: Optional[ResolutionIntent] = None, namespace: Optional[str] = None,
                      vector: Optional[Any] = None, timestamp: Optional[Union[datetime, str]] = None) -> MemoryDecision:
        effective_namespace = namespace or self.namespace
        final_timestamp = datetime.now()
        if timestamp:
            if isinstance(timestamp, str):
                try:
                    iso_str = timestamp.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(iso_str)
                    final_timestamp = dt.replace(microsecond=(dt.microsecond // 1000) * 1000)
                except Exception: final_timestamp = datetime.now().replace(microsecond=0)
            else: final_timestamp = timestamp.replace(microsecond=(timestamp.microsecond // 1000) * 1000)

        # Build and Validate event
        event = MemoryEvent(source=source, kind=kind, content=content, context=context or {}, timestamp=final_timestamp)
        if self.episodic.find_duplicate(event, ignore_links=True).value:
            return MemoryDecision(should_persist=False, store_type="none", reason="Duplicate event detected")

        decision = self.router.route(event, intent=intent)
        if decision and decision.should_persist and decision.store_type == "semantic" and not intent:
             if conflict_msg := self.conflict_engine.check_for_conflicts(event, namespace=effective_namespace):
                 return MemoryDecision(should_persist=False, store_type="none", reason=f"Invariant Violation: {conflict_msg}")
        
        if decision and decision.should_persist:
            if decision.store_type == "episodic":
                if source in {"user", "agent"}:
                    ev_id = self.episodic.append(event).value
                    decision.metadata["event_id"] = ev_id
            elif decision.store_type == "semantic":
                with self.semantic.transaction():
                    if intent and intent.resolution_type == "supersede":
                        for old_id in intent.target_decision_ids:
                            old_meta = self.semantic.meta.get_by_fid(old_id)
                            if old_meta and old_meta.get('status') == 'active':
                                self.semantic.update_decision(old_id, {"status": "superseded"}, commit_msg="Deactivating for transition")

                    if isinstance(event.context, (DecisionContent, DecisionStream, ProposalContent)):
                        if intent and intent.resolution_type == "supersede":
                            event.context.supersedes = intent.target_decision_ids
                        event.context.namespace = effective_namespace
                        event.context = event.context.model_dump(mode='json')
                    elif isinstance(event.context, dict):
                        if intent and intent.resolution_type == "supersede":
                            event.context["supersedes"] = intent.target_decision_ids
                        event.context["namespace"] = effective_namespace

                    new_fid = self.semantic.save(event, namespace=effective_namespace)
                    decision.metadata["file_id"] = new_fid

                    if intent and intent.resolution_type == "supersede":
                        for old_id in intent.target_decision_ids:
                            self.semantic.update_decision(old_id, {"status": "superseded", "superseded_by": new_fid}, commit_msg=f"Superseded by {new_fid}")

                    # Grounding
                    all_grounding_ids = set()
                    if isinstance(event.context, dict): all_grounding_ids.update(event.context.get('evidence_event_ids', []))
                    if intent and intent.resolution_type == "supersede":
                        try:
                            old_links_map = self.episodic.get_linked_event_ids_batch(intent.target_decision_ids)
                            for old_id in intent.target_decision_ids:
                                if old_id in old_links_map: all_grounding_ids.update(old_links_map[old_id])
                        except Exception: pass

                    for ev_id in all_grounding_ids:
                        try: self.episodic.link_to_semantic(ev_id, new_fid)
                        except Exception: pass

                if vector is not None:
                    try:
                        self.vector.add_documents([{"id": new_fid, "content": f"{event.content}\n{event.context.get('rationale', '')}"}], embeddings=[vector])
                    except Exception: pass

                if source in {"user", "agent"}:
                    ev_id = self.episodic.append(event, linked_id=new_fid).value
                    decision.metadata["event_id"] = ev_id
        return decision

    def update_decision(self, decision_id: str, updates: Dict[str, Any], commit_msg: str, skip_episodic: bool = False) -> bool:
        self.semantic._validate_fid(decision_id)
        def _json_safe(v):
            if hasattr(v, 'value'): return v.value
            if isinstance(v, datetime): return v.isoformat()
            if isinstance(v, (list, dict)): return json.loads(json.dumps(v, default=str))
            return v
        updates = {k: _json_safe(v) for k, v in updates.items()}

        current_meta = self.semantic.meta.get_by_fid(decision_id)
        if not current_meta: return False
        
        with self.semantic.transaction():
            self.semantic.update_decision(decision_id, updates, commit_msg)
            if "content" in updates or "rationale" in updates:
                meta = self.semantic.meta.get_by_fid(decision_id)
                if meta:
                    try: self.vector.add_documents([{"id": decision_id, "content": meta.get('content', '')}])
                    except Exception: pass
            
            if not skip_episodic:
                self.episodic.append(MemoryEvent(source="system", kind="commit_change", 
                                                 content=f"Updated {current_meta.get('kind')}: {current_meta.get('title')}",
                                                 context={"updates": updates, "rationale": commit_msg}), linked_id=decision_id)
        return True

    def run_maintenance(self, stop_event: Optional[threading.Event] = None) -> Dict[str, Any]:
        """Runs periodic maintenance tasks. Supports interruption via stop_event."""
        self.semantic.sync_meta_index()
        integrity_status = "ok"
        
        if stop_event and stop_event.is_set(): return {"integrity": "aborted"}

        # 0. Lifecycle & Reflection
        reflection_proposals = self.run_reflection(stop_event=stop_event)
        if stop_event and stop_event.is_set(): return {"integrity": integrity_status, "reflection": "aborted"}

        decay_report = self.run_decay(stop_event=stop_event)
        if stop_event and stop_event.is_set(): return {"integrity": integrity_status, "decay": "aborted"}

        # 1. Vector Sync
        self.reindex_missing(stop_event=stop_event)
        if stop_event and stop_event.is_set(): return {"integrity": integrity_status, "vector_sync": "aborted"}

        # 2. Merging
        from ledgermind.core.reasoning.merging import MergeEngine
        merger = MergeEngine(self)
        merges = merger.scan_for_duplicates()

        return {
            "decay": decay_report.__dict__ if hasattr(decay_report, '__dict__') else str(decay_report),
            "reflection": {"proposals_created": len(reflection_proposals)},
            "merging": {"proposals_created": len(merges), "ids": merges},
            "integrity": integrity_status
        }

    def run_reflection(self, stop_event: Optional[threading.Event] = None) -> List[str]:
        watermark_key = "last_reflection_event_id"
        after_id = int(self.semantic.meta.get_config(watermark_key) or 0)
        all_proposal_ids = []
        CHUNK_SIZE, MAX_TOTAL = 5000, 100000
        processed = 0
        
        while processed < MAX_TOTAL:
            if stop_event and stop_event.is_set(): break
            proposal_ids, new_max_id = self.reflection_engine.run_cycle(after_id=after_id, limit=CHUNK_SIZE)
            if new_max_id is None or new_max_id <= after_id: break
            all_proposal_ids.extend(proposal_ids)
            after_id = new_max_id
            processed += CHUNK_SIZE
            self.semantic.meta.set_config(watermark_key, str(new_max_id))
            if len(proposal_ids) < CHUNK_SIZE / 2: break
        return all_proposal_ids

    def run_decay(self, stop_event: Optional[threading.Event] = None) -> DecayReport:
        all_events = self.episodic.query(limit=20000, status=None)
        to_archive, to_prune, retained = self.decay_engine.evaluate(all_events)
        all_decisions = self.semantic.meta.list_all()
        semantic_results = self.decay_engine.evaluate_semantic(all_decisions)
        
        forgotten_count = 0
        with self.semantic.transaction():
            self.episodic.mark_archived(to_archive)
            self.episodic.physical_prune(to_prune)
            for fid, new_conf, should_forget in semantic_results:
                if stop_event and stop_event.is_set(): break
                if should_forget:
                    self.forget(fid)
                    forgotten_count += 1
                else:
                    self.semantic.update_decision(fid, {"confidence": new_conf}, commit_msg=f"Decay: {new_conf}")
        return DecayReport(len(to_archive), len(to_prune), retained, semantic_forgotten=forgotten_count)

    def search_decisions(self, query: str, limit: int = 5, offset: int = 0, namespace: Optional[str] = None, mode: str = "balanced") -> List[Dict[str, Any]]:
        effective_namespace = namespace or self.namespace
        k = 60
        search_limit = max(200, (offset + limit) * 5)
        vec_results = []
        try: vec_results = self.vector.search(query, limit=search_limit)
        except Exception: pass
        kw_results = self.semantic.meta.keyword_search(query, limit=search_limit, namespace=effective_namespace)
        
        all_fids = list(set([item['id'] for item in vec_results] + [r[0] for r in kw_results]))
        meta_cache = {m['fid']: m for m in self.semantic.meta.get_batch_by_fids(all_fids)}
        
        scores = {}
        for rank, item in enumerate(vec_results):
            fid = item['id']
            meta = meta_cache.get(fid)
            weight = 1.35 if meta and meta.get('kind') == 'decision' else 1.0
            scores[fid] = scores.get(fid, 0.0) + (weight / (k + rank + 1))
        for rank, r in enumerate(kw_results):
            fid = r[0]
            meta = meta_cache.get(fid)
            weight = 1.35 if meta and meta.get('kind') == 'decision' else 1.0
            scores[fid] = scores.get(fid, 0.0) + (weight / (k + rank + 1))

        sorted_fids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        final_results = []
        TECHNICAL_STATUSES = ("processed", "knowledge_merge", "knowledge_validation", "accepted")
        
        for fid in sorted_fids:
            meta = self.semantic.meta.resolve_to_truth(fid)
            if not meta or meta.get('namespace', 'default') != effective_namespace: continue
            status = meta.get("status", "unknown")
            if status in TECHNICAL_STATUSES: continue
            
            # Whitelist pending_merge
            if not self.include_history and status not in ("active", "superseded", "deprecated", "pending_merge"): continue
            if mode == "strict" and status not in ("active", "pending_merge"): continue
            
            try: ctx = json.loads(meta.get('context_json', '{}'))
            except: ctx = {}
            
            final_results.append({
                "id": meta['fid'], "score": scores[fid], "status": status, "title": meta.get("title"),
                "target": meta.get("target"), "content": meta.get("content"), "rationale": ctx.get("rationale")
            })
            if len(final_results) >= limit + offset: break
        return final_results[offset:]

    def reindex_missing(self, limit: int = 50, stop_event: Optional[threading.Event] = None):
        if not self.vector: return
        try:
            active_metas = [m for m in self.semantic.meta.list_all() if m.get('status') == 'active']
            indexed_ids = set(self.vector.get_all_ids())
            missing = [m for m in active_metas if m['fid'] not in indexed_ids]
            if not missing: return
            
            docs = []
            for m in missing[:limit]:
                if stop_event and stop_event.is_set(): break
                try:
                    ctx = json.loads(m.get('context_json', '{}'))
                    docs.append({"id": m['fid'], "content": f"{m.get('title', '')}\n{ctx.get('rationale', '')}"})
                except Exception: pass
            if docs: self.vector.add_documents(docs)
        except Exception as e: logger.error(f"Reindex failed: {e}")

    def forget(self, decision_id: str):
        self.semantic._validate_fid(decision_id)
        self.episodic.unlink_all_for_semantic(decision_id)
        self.semantic.purge_memory(decision_id)
        self.vector.remove_id(decision_id)

    def close(self):
        if hasattr(self, 'vector'): self.vector.close()
        if hasattr(self, 'semantic') and hasattr(self.semantic, 'meta'): self.semantic.meta.close()
