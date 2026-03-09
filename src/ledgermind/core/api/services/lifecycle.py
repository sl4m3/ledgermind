import logging
import threading
from typing import List, Dict, Any, Optional
from ..base_service import MemoryService
from ledgermind.core.reasoning.decay import DecayReport

logger = logging.getLogger("ledgermind.core.api.services.lifecycle")

class LifecycleManagementService(MemoryService):
    """
    Service responsible for knowledge lifecycle management: 
    decay, reflection, maintenance, and re-indexing.
    """
    
    @property
    def decay_engine(self):
        return self.context.decay_engine
        
    @property
    def reflection_engine(self):
        return self.context.reflection_engine

    def run_decay(self, dry_run: bool = False, stop_event: Optional[threading.Event] = None) -> DecayReport:
        """Execute the decay process for episodic and semantic memories."""
        # 1. Episodic Decay
        all_events = self.episodic.query(limit=20000, status=None)
        to_archive, to_prune, retained = self.decay_engine.evaluate(all_events)
        
        # 2. Semantic Decay
        all_decisions = self.semantic.meta.list_all()
        semantic_results = self.decay_engine.evaluate_semantic(all_decisions)
        
        forgotten_count = 0
        if not dry_run:
            with self.transaction(description="Memory Decay"):
                self.episodic.mark_archived(to_archive)
                self.episodic.physical_prune(to_prune)
                
                for fid, new_conf, should_forget in semantic_results:
                    if stop_event and stop_event.is_set():
                        logger.info("Decay: Interrupted by stop event.")
                        break

                    if should_forget:
                        meta = self.semantic.meta.get_by_fid(fid)
                        kind = meta.get('kind') if meta else None
                        
                        if kind in ('decision', 'constraint', 'intervention', 'proposal'):
                             logger.info(f"Semantic Decay: Marking {fid} as dormant/deprecated (conf={new_conf})")
                             self.semantic.update_decision(fid, {"confidence": 0.0, "status": "deprecated", "vitality": "dormant"}, 
                                                         commit_msg=f"Decay: Knowledge reached zero confidence, marked as dormant.")
                        else:
                             logger.info(f"Semantic Decay: Forgetting {fid} (conf={new_conf})")
                             # Note: assuming forget logic is simple enough or delegated
                             self.semantic.purge_memory(fid)
                             self.vector.remove_id(fid)
                             forgotten_count += 1
                    else:
                        updates = {"confidence": new_conf}
                        meta = self.semantic.meta.get_by_fid(fid)
                        if meta:
                            if meta.get('status') == 'active' and new_conf < 0.5:
                                updates["status"] = "deprecated"
                            if meta.get('vitality') == 'active' and new_conf < 0.9:
                                updates["vitality"] = "decaying"
                        
                        self.semantic.update_decision(fid, updates, commit_msg=f"Decay: Reduced confidence to {new_conf}")
            
        return DecayReport(len(to_archive), len(to_prune), retained, semantic_forgotten=forgotten_count)

    def run_reflection(self, stop_event: Optional[threading.Event] = None) -> List[str]:
        """Execute the incremental reflection process."""
        watermark_key = "last_reflection_event_id"
        last_id = self.semantic.meta.get_config(watermark_key)
        after_id = int(last_id) if last_id is not None else 0
        
        all_proposal_ids = []
        CHUNK_SIZE = 5000
        MAX_TOTAL = 100000 
        processed_total = 0
        
        while processed_total < MAX_TOTAL:
            if stop_event and stop_event.is_set():
                logger.info("Reflection: Interrupted by stop event.")
                break

            proposal_ids, new_max_id = self.reflection_engine.run_cycle(after_id=after_id, limit=CHUNK_SIZE)
            
            if new_max_id is None or new_max_id <= after_id: break
                
            all_proposal_ids.extend(proposal_ids)
            after_id = new_max_id
            processed_total += CHUNK_SIZE
            
            # Using semantic direct lock for watermark update as in original code
            if self.semantic._fs_lock.acquire(exclusive=True, timeout=30):
                try:
                    self.semantic.meta.set_config(watermark_key, str(new_max_id))
                finally:
                    self.semantic._fs_lock.release()

        return all_proposal_ids

    def run_maintenance(self, stop_event: Optional[threading.Event] = None) -> Dict[str, Any]:
        """Runs periodic maintenance tasks."""
        from ledgermind.core.stores.semantic_store.integrity import IntegrityChecker
        self.semantic.sync_meta_index()
        integrity_status = "ok"
        try:
            IntegrityChecker.validate(self.semantic.repo_path, force=True)
        except Exception as ie:
            logger.error(f"Integrity Violation: {ie}")
            integrity_status = f"violation: {str(ie)}"

        if stop_event and stop_event.is_set(): return {"integrity": integrity_status}

        reflection_proposals = self.run_reflection(stop_event=stop_event)
        if stop_event and stop_event.is_set(): 
            return {"integrity": integrity_status, "reflection": {"proposals_created": len(reflection_proposals)}}

        decay_report = self.run_decay(stop_event=stop_event)
        
        # Stats update logic moved to health service usually, but kept here for now or delegated
        if stop_event and stop_event.is_set(): 
            return {"integrity": integrity_status, "decay": decay_report.__dict__}

        from ledgermind.core.reasoning.merging import MergeEngine
        self.reindex_missing(stop_event=stop_event)

        if stop_event and stop_event.is_set(): 
            return {"integrity": integrity_status, "decay": decay_report.__dict__}

        # Passing self.context to MergeEngine might require a shim or update to MergeEngine
        # For now, maintenance continues to orchestrate
        from ledgermind.core.api.memory import Memory # Temporary for compatibility
        memory_proxy = self.context.lifecycle.processor if hasattr(self.context.lifecycle, 'processor') else None
        
        # MergeEngine currently expects a Memory-like object.
        # We'll use a hack or ensure MergeEngine is updated.
        from ledgermind.core.reasoning.merging import MergeEngine
        # ... implementation of merger invocation ...
        return {
            "decay": decay_report.__dict__,
            "reflection": {"proposals_created": len(reflection_proposals)},
            "integrity": integrity_status
        }

    def reindex_missing(self, limit: int = 50, stop_event: Optional[threading.Event] = None):
        """Identifies active decisions missing from the vector index."""
        if not self.vector: return
        try:
            all_metas = self.semantic.meta.list_all()
            target_metas = [m for m in all_metas if m.get('status') in ('active', 'draft')]
            if not target_metas: return
            
            indexed_ids = set(self.vector.get_all_ids())
            missing = [m for m in target_metas if m['fid'] not in indexed_ids]
            if not missing: return
                
            logger.info(f"Re-indexing {len(missing)} missing entries...")
            docs_to_add = []
            for m in missing[:limit]:
                if stop_event and stop_event.is_set(): break
                try:
                    import json
                    ctx = json.loads(m.get('context_json', '{}'))
                    rationale = ctx.get('rationale', '') or m.get('content', '')
                    docs_to_add.append({
                        "id": m['fid'],
                        "content": f"{m.get('title', '')}\n{rationale}",
                        "metadata": {"target": m.get('target'), "kind": m.get('kind')}
                    })
                except Exception as e:
                    logger.warning(f"Failed to prepare {m['fid']}: {e}")
            
            if docs_to_add:
                self.vector.add_documents(docs_to_add, stop_event=stop_event)
                self.vector.save()
        except Exception as e:
            logger.error(f"Auto-reindexing failed: {e}")
