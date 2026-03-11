import os
import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from ..base_service import MemoryService
from ledgermind.core.core.schemas import (
    MemoryDecision, ResolutionIntent, DecisionStream, DecisionPhase, 
    DecisionVitality, KIND_DECISION, KIND_PROPOSAL
)
from ledgermind.core.core.exceptions import InvariantViolation, ConflictError

logger = logging.getLogger("ledgermind.core.api.services.decision_command")

class DecisionCommandService(MemoryService):
    """
    Service responsible for high-level decision management commands:
    recording, superseding, updating, and accepting proposals.
    """
    
    def record_decision(self, title: str, target: str, rationale: str, 
                        consequences: Optional[List[str]] = None, 
                        evidence_ids: Optional[List[int]] = None, 
                        namespace: Optional[str] = None, 
                        arbiter_callback: Optional[callable] = None,
                        memory_facade: Any = None) -> MemoryDecision:
        """Helper to record a new decision."""
        if not title.strip(): raise ValueError("Title cannot be empty")
        if not target.strip(): raise ValueError("Target cannot be empty")
        if not rationale.strip(): raise ValueError("Rationale cannot be empty")

        effective_namespace = namespace or self.context.namespace
        target = self.context.targets.normalize(target)
        self.context.targets.register(target, description=title)

        active_conflicts = self.semantic.list_active_conflicts(target, namespace=effective_namespace)
        new_vec_cached = None

        # V7.5: Ensure conflict analysis works even without vector model
        try:
            import numpy as np
            from difflib import SequenceMatcher
            new_text = f"{title}\n{rationale}"

            if self.vector:
                from ledgermind.core.stores.vector import _is_transformers_available
                can_compute = _is_transformers_available() or (hasattr(self.vector, "model") and self.vector.model is not None)
                if can_compute:
                    new_vec = self.vector.model.encode([new_text])[0]
                    new_vec_cached = new_vec
                    new_norm = np.linalg.norm(new_vec)

            if active_conflicts:
                for old_fid in active_conflicts:
                    old_meta = self.semantic.meta.get_by_fid(old_fid)
                    if not old_meta: continue

                    sim = 0.0
                    if new_vec_cached is not None:
                        old_vec = self.vector.get_vector(old_fid)
                        if old_vec is not None:
                            old_norm = np.linalg.norm(old_vec)
                            sim = float(np.dot(new_vec_cached, old_vec) / (new_norm * old_norm + 1e-9))

                    # Text-based fallback if vector failed or unavailable
                    old_title = old_meta.get('title', '')
                    old_content = old_meta.get('content', '')
                    title_sim = SequenceMatcher(None, title.lower(), old_title.lower()).ratio()
                    content_sim = SequenceMatcher(None, new_text.lower(), old_content.lower()).ratio()

                    # Elevate similarity if titles match
                    if title_sim > 0.90: sim = max(sim, 0.86)
                    # Support Arbiter in the Gray Zone (0.50 - 0.85)
                    if 0.50 <= max(sim, content_sim) < 0.85 and arbiter_callback:
                        if arbiter_callback({"title": title, "rationale": rationale}, {"title": old_title, "rationale": old_content}) == "SUPERSEDE":
                            sim = 0.86

                    # Take best similarity
                    sim = max(sim, content_sim)

                    if sim > 0.85:
                        return self.supersede_decision(
                            title=title, target=target,
                            rationale=f"Auto-Evolution: Updated based on high similarity ({sim:.2f}). {rationale}",
                            old_decision_ids=[old_fid], consequences=consequences, evidence_ids=evidence_ids,
                            namespace=effective_namespace, vector=new_vec_cached, memory_facade=memory_facade
                        )
        except Exception as e:
            if "not found" not in str(e).lower() and "missing" not in str(e).lower():
                logger.warning(f"Conflict resolution fallback failed: {e}", exc_info=True)
        
        if active_conflicts:
            msg = f"CONFLICT: Target '{target}' in namespace '{effective_namespace}' already has active decisions: {active_conflicts}."
            raise ConflictError(msg)

        ctx = DecisionStream(
            decision_id=str(uuid.uuid4()), title=title, target=target, rationale=rationale,
            consequences=consequences or [], evidence_event_ids=evidence_ids or [], namespace=effective_namespace
        )
        ctx = self.context.lifecycle.process_intervention(ctx, datetime.now())

        decision = memory_facade.process_event(
            source="agent", kind=KIND_DECISION, content=title, context=ctx,
            namespace=effective_namespace, vector=new_vec_cached
        )
        if not decision.should_persist:
            raise InvariantViolation(f"Failed to record decision: {decision.reason}")
        return decision

    def supersede_decision(self, title: str, target: str, rationale: str, 
                           old_decision_ids: List[str], 
                           consequences: Optional[List[str]] = None, 
                           evidence_ids: Optional[List[int]] = None, 
                           namespace: Optional[str] = None, 
                           vector: Optional[Any] = None,
                           memory_facade: Any = None) -> MemoryDecision:
        """Helper to evolve knowledge."""
        effective_namespace = namespace or self.context.namespace
        for oid in old_decision_ids:
            meta = self.semantic.meta.get_by_fid(oid)
            if not meta: raise ConflictError(f"Cannot supersede {oid}: missing.")
            if meta.get('status') not in ('active', 'pending_merge', 'accepted', 'draft'):
                raise ConflictError(f"Cannot supersede {oid}: status {meta.get('status')}.")

        intent = ResolutionIntent(resolution_type="supersede", rationale=rationale, target_decision_ids=old_decision_ids)
        ctx = DecisionStream(
            decision_id=str(uuid.uuid4()), title=title, target=target, rationale=rationale,
            status="active",
            consequences=consequences or [], evidence_event_ids=evidence_ids or [], namespace=effective_namespace,
            phase=DecisionPhase.EMERGENT, vitality=DecisionVitality.ACTIVE, first_seen=datetime.now(), last_seen=datetime.now()
        )
        decision = memory_facade.process_event(
            source="agent", kind=KIND_DECISION, content=title, context=ctx,
            intent=intent, namespace=effective_namespace, vector=vector
        )
        if not decision.should_persist:
            raise InvariantViolation(f"Failed to supersede decision: {decision.reason}")
        return decision

    def accept_proposal(self, proposal_id: str, memory_facade: Any) -> MemoryDecision:
        """Converts a proposal into an active decision."""
        self.semantic._validate_fid(proposal_id)
        from ledgermind.core.stores.semantic_store.loader import MemoryLoader
        file_path = os.path.join(self.semantic.repo_path, proposal_id)
        if not os.path.exists(file_path): raise FileNotFoundError(f"Proposal not found: {proposal_id}")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            data, _ = MemoryLoader.parse(f.read())
        
        if data.get("kind") != "proposal": raise ValueError(f"Not a proposal: {proposal_id}")
        
        # V7.0: Status is a root field in metadata
        ctx = data.get("context", {})
        current_status = data.get("status") or ctx.get("status", "")
        if str(current_status).lower() != "draft": raise ValueError(f"Not draft: {proposal_id}")

        try:
            with self.transaction(description=f"Accept Proposal {proposal_id}"):
                supersedes = ctx.get("suggested_supersedes", [])
                target, title, enrichment_status, final_rationale = ctx.get("target"), ctx.get("title"), ctx.get("enrichment_status"), ctx.get("rationale", "")

                if target == "knowledge_merge" and supersedes:
                    if enrichment_status != "completed":
                        original_rationales = []
                        for sid in supersedes:
                            try:
                                s_data = self.semantic.get_decision(sid)
                                if s_data and s_data.rationale: original_rationales.append(s_data.rationale)
                            except Exception: continue
                        if original_rationales:
                            from ledgermind.core.reasoning.llm_enrichment import LLMEnricher
                            mode = self.semantic.meta.get_config("arbitration_mode", "lite")
                            final_rationale = LLMEnricher(mode=mode).synthesize_merged_rationale(original_rationales)
                else:
                    if enrichment_status != "completed":
                        final_rationale = f"Accepted proposal {proposal_id}. {final_rationale}"

                grounding_ids = set(ctx.get("evidence_event_ids", []))
                if supersedes:
                    for sid in supersedes:
                        try:
                            old_data = self.semantic.meta.get_by_fid(sid)
                            if old_data and old_data.get('context_json'):
                                grounding_ids.update(json.loads(old_data['context_json']).get('evidence_event_ids', []))
                        except Exception: pass

                try: grounding_ids.update(self.episodic.get_linked_event_ids(proposal_id))
                except Exception: pass
                
                decision = self.supersede_decision(
                    title=title, target=target, rationale=final_rationale,
                    old_decision_ids=list(set([proposal_id] + (supersedes or []))),
                    consequences=ctx.get("suggested_consequences", []), evidence_ids=list(grounding_ids), memory_facade=memory_facade
                )
                
                if decision.should_persist:
                    self.semantic.update_decision(proposal_id, {"status": "accepted", "converted_to": decision.metadata.get("file_id")}, commit_msg=f"Accepted and converted")
        except Exception as e:
            logger.warning(f"Proposal conversion failed: {e}")
            try: self.semantic.update_decision(proposal_id, {"status": "draft"}, f"Conversion failed: {str(e)}")
            except Exception: pass
            raise
        return decision

    def reject_proposal(self, proposal_id: str, reason: str):
        """Marks a proposal as rejected."""
        self.semantic._validate_fid(proposal_id)
        self.semantic.update_decision(proposal_id, {"status": "rejected", "rejection_reason": reason}, commit_msg=f"Rejected: {reason}")

    def update_decision(self, decision_id: str, updates: Dict[str, Any], commit_msg: str, skip_episodic: bool = False) -> bool:
        """Coordinates updates to a semantic record."""
        self.semantic._validate_fid(decision_id)
        
        def _json_safe(v):
            if hasattr(v, 'value'): return v.value
            if isinstance(v, datetime): return v.isoformat()
            if isinstance(v, list): return [_json_safe(item) for item in v]
            if isinstance(v, dict): return {k: _json_safe(val) for k, val in v.items()}
            return v

        updates = {k: _json_safe(v) for k, v in updates.items()}
        current_meta = self.semantic.meta.get_by_fid(decision_id)
        if current_meta:
            current_ctx = json.loads(current_meta.get('context_json', '{}'))
            if not any(current_meta.get(k) != v and current_ctx.get(k) != v for k, v in updates.items()):
                return True

        with self.transaction(description=f"Update Decision {decision_id}"):
            self.semantic.update_decision(decision_id, updates, commit_msg)
            if "content" in updates or "rationale" in updates:
                meta = self.semantic.meta.get_by_fid(decision_id)
                if meta:
                    try: self.vector.add_documents([{"id": decision_id, "content": meta.get('content', '')}])
                    except Exception: pass
            
            if not skip_episodic:
                meta = self.semantic.meta.get_by_fid(decision_id)
                if meta:
                    old_phase, new_phase = current_ctx.get('phase'), updates.get('phase')
                    if new_phase and old_phase != new_phase:
                        from ledgermind.core.core.schemas import MemoryEvent
                        self.episodic.append(MemoryEvent(source="system", kind="commit_change", content=f"Lifecycle change for {meta.get('title')}", context={"fid": decision_id, "old_phase": old_phase, "new_phase": new_phase}), linked_id=decision_id)
                    # Additional logging logic as per original code...
        return True
