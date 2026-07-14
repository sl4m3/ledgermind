from typing import List, Dict, Any, Optional
import logging
import functools
import random
from .algorithm_factory import AlgorithmFactory
from .transaction_manager import TransactionManager
from .validator import DuplicateValidator
from .config import MergeConfig
from .types import MemoryProtocol, Result
from .builder import ProposalBuilder

logger = logging.getLogger("ledgermind.core.merging.facade")


class MergeEngineFacade:
    """Main interface (facade) for working with the merge subsystem (MergeEngine)."""

    def __init__(self, memory: MemoryProtocol, config: Optional[MergeConfig] = None):
        self.memory = memory
        self.config = config or MergeConfig()
        self.transaction_manager = TransactionManager(memory)
        self.validator = DuplicateValidator()

        # Dynamic algorithm loading through factory
        alg_config = self.config.get_algorithm_config("default")
        alg_name = alg_config.get("name", "vector_embedding")

        self.algorithm = AlgorithmFactory.create(
            alg_name,
            threshold=self.config.get_algorithm_config("default").get(
                "validation_threshold", 0.60
            ),
        )

    def scan_for_duplicates(
        self, candidates: List[Dict[str, Any]], threshold: Optional[float] = None
    ) -> Result:
        """
        High-performance clustered scan focusing on stable (completed) and active truths.
        Implements Stage 1 (Clustering) and Stage 3 (Pruning/Truth Resolution) of the plan.
        """
        logger.info(f"Starting clustered scan. Initial candidates: {len(candidates)}")

        # 1. PRE-PROCESSING: Local metadata cache of 'True' and 'Completed' versions
        resolved_candidates = []
        meta_cache = {}

        # Load all metadata once to avoid DB hits in the loop
        all_metadata = self.memory.semantic.meta.list_all()
        # Build a fast lookup map
        full_meta_map = {m.get("fid", m.get("id")): m for m in all_metadata if m}

        for cand in candidates:
            cand_id = cand.get("fid", cand.get("id"))

            # Resolve to the latest version using internal QueryService logic
            resolved = self.memory._resolve_to_truth(
                cand_id, mode="balanced", cache=full_meta_map
            )
            if not resolved:
                continue

            # FILTER: Only stable knowledge (Stage 3)
            if resolved.get("status") in (
                "superseded",
                "deprecated",
                "rejected",
                "falsified",
            ):
                continue

            # FILTER: Must be enriched to have reliable semantic data
            if resolved.get("enrichment_status") != "completed":
                continue

            fid = resolved.get("fid")
            if fid not in meta_cache:
                meta_cache[fid] = resolved
                resolved_candidates.append(resolved)

        logger.info(
            f"Filtered to {len(resolved_candidates)} stable active truths for clustering."
        )

        # V7.7: RANDOMIZE ORDER to avoid processing same candidates every cycle
        # This prevents "merge loops" where the same cluster is always selected
        random.shuffle(resolved_candidates)
        logger.debug(f"Shuffled candidates for diverse merge exploration.")

        # 2. PRE-CACHE EMBEDDINGS (Batch optimization)
        # Only load model if there are candidates to process
        if not resolved_candidates:
            logger.info("No candidates to process, skipping merge.")
            return Result(success=True, data=[], metadata={"candidates": 0})

        # Model will be loaded on-demand by calculate_similarity()
        # No pre-caching needed — vectors already in index, Annoy already built

        proposals = []

        # Use thresholds from config if available, otherwise fall back to defaults
        merge_threshold = self.config.threshold or 0.80

        try:
            for i, candidate in enumerate(resolved_candidates):
                cand_id = candidate.get("fid")

                # RE-VALIDATE: Check actual merge status from DB before processing
                current_meta = self.memory.semantic.meta.get_by_fid(cand_id)
                if not current_meta or current_meta.get("merge_status") == "pending":
                    continue

                query_text = self.algorithm._get_doc_text(candidate)
                if not query_text.strip():
                    continue

                # 3. FAST SEARCH: Use vector index (Stage 1 search)
                search_results = self.memory.vector.search(query_text, limit=30)
                if not search_results:
                    continue

                to_merge = []
                seen_target_fids = set()

                for res in search_results:
                    doc_id = res.get("id")
                    if doc_id == cand_id:
                        continue

                    target_doc = self.memory._resolve_to_truth(
                        doc_id, mode="balanced", cache=full_meta_map
                    )
                    if not target_doc:
                        continue

                    target_fid = target_doc.get("fid")

                    # Prevent self-merging (resolved truth is the candidate itself)
                    if target_fid == cand_id:
                        continue

                    # Prevent duplicate targets in the same group
                    if target_fid in seen_target_fids:
                        continue
                    seen_target_fids.add(target_fid)

                    # IMPORTANT: Check if target is already being merged
                    actual_target = self.memory.semantic.meta.get_by_fid(target_fid)
                    if (
                        not actual_target
                        or actual_target.get("merge_status") == "pending"
                    ):
                        continue

                    # ALLOW: 'active' AND 'draft' for merging
                    if actual_target.get("status") not in ("active", "draft"):
                        continue

                    if actual_target.get("enrichment_status") != "completed":
                        continue

                    # 4. FAST COMPARISON (Will use pre-cached embeddings)
                    sim_score = self.algorithm.calculate_similarity(
                        candidate, actual_target, memory=self.memory
                    )

                    if sim_score >= merge_threshold:
                        to_merge.append(actual_target)

                if to_merge:
                    group = [candidate] + to_merge

                    if len(group) < 2:
                        continue

                    topic = f"Merge Cluster: {candidate.get('topic', candidate.get('title', 'Knowledge Group'))}"

                    pid = self.execute_merge_transaction(
                        group, topic=topic, target="knowledge_merge"
                    )
                    if pid:
                        proposals.append(pid)
                        # CRITICAL: Invalidate global meta cache so next iterations see 'pending' status
                        if hasattr(self.memory.semantic.meta, "clear_cache"):
                            self.memory.semantic.meta.clear_cache()

            return Result(success=True, data=proposals)
        except Exception as e:
            logger.error(f"Critical error during scan: {e}", exc_info=True)
            return Result(success=False, error=str(e))

    def execute_merge_transaction(
        self, group: List[Dict[str, Any]], topic: str, target: str
    ) -> Optional[str]:
        """Atomically creates a merge proposal and updates all target statuses."""
        try:
            with self.memory.semantic.transaction():
                # 1. Build and Save Proposal
                builder = ProposalBuilder(self.memory)
                builder.set_target(target)
                builder.set_topic(topic)

                # Average confidence
                base_doc = group[0]
                sim_scores = [
                    self.algorithm.calculate_similarity(base_doc, doc)
                    for doc in group[1:]
                ]
                avg_confidence = (
                    sum(sim_scores) / len(sim_scores) if sim_scores else 1.0
                )
                builder.set_confidence(avg_confidence)

                # V7.8: Deduplicate group by fid to avoid adding same target multiple times
                seen_fids = set()
                for doc in group:
                    # Use fid as primary key (consistent with semantic store)
                    fid = doc.get("fid") or doc.get("id")
                    if fid and fid not in seen_fids:
                        seen_fids.add(fid)
                        builder.add_target(fid)

                proposal_data = builder.build()
                proposal_fid = self.transaction_manager.create_proposal(proposal_data)

                if not proposal_fid:
                    raise Exception("Failed to save merge proposal file.")

                # 2. Mark all targets as 'pending merge' IMMEDIATELY in the same transaction
                # V7.8: Deduplicate to avoid updating same target multiple times
                reserved_fids = set()
                for doc in group:
                    fid = doc.get("fid") or doc.get("id")
                    if not fid or fid in reserved_fids:
                        continue
                    reserved_fids.add(fid)

                    # We ONLY set merge_status. We DO NOT set superseded_by yet,
                    # because this is just a proposal, not a confirmed truth.
                    updates = {"merge_status": "pending"}
                    self.memory.semantic.update_decision(
                        fid,
                        updates,
                        commit_msg=f"Reserved for merge proposal {proposal_fid}",
                    )
                    logger.info(
                        f"Target {fid} is now RESERVED for merge {proposal_fid}"
                    )

                return proposal_fid

        except Exception as e:
            logger.error(f"Failed atomic merge transaction: {e}")
            return None

    def create_merge_proposal(
        self,
        group: List[Dict[str, Any]],
        topic: Optional[str] = None,
        confidence: Optional[float] = None,
        target: str = "knowledge_merge",
    ) -> Optional[str]:
        """Creates a proposal using Builder."""
        error = self.validator.validate_group(group)
        if error:
            logger.warning(f"Group validation failed: {error}")
            return None

        try:
            builder = ProposalBuilder(self.memory)
            builder.set_target(target)

            if topic:
                builder.set_topic(topic)
            else:
                builder.set_topic(f"Merging {len(group)} documents")

            if confidence is not None:
                builder.set_confidence(confidence)
            else:
                # Calculate average confidence for the group
                base_doc = group[0]
                sim_scores = [
                    self.algorithm.calculate_similarity(base_doc, doc)
                    for doc in group[1:]
                ]
                avg_confidence = (
                    sum(sim_scores) / len(sim_scores) if sim_scores else 0.0
                )
                builder.set_confidence(avg_confidence)

            for doc in group:
                builder.add_target(doc.get("id", doc.get("fid", "unknown_id")))

            proposal_data = builder.build()
            return self.transaction_manager.create_proposal(proposal_data)
        except ValueError as ve:
            logger.warning(f"Could not build proposal: {ve}")
            return None


class MergeEngine:
    """Wrapper class for backward compatibility with the old API."""

    def __init__(self, memory: MemoryProtocol, config: Optional[MergeConfig] = None):
        self.memory = memory
        self.config = config or MergeConfig()
        self._facade = MergeEngineFacade(memory, self.config)

    def scan_for_duplicates(self, threshold: Optional[float] = None) -> List[str]:
        try:
            # Emulation: take everything from memory
            all_candidates = self.memory.semantic.meta.list_all()
            result = self._facade.scan_for_duplicates(all_candidates, threshold)
            return result.data if result.success else []
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            return []

    def _calculate_jaccard(
        self,
        text1: str,
        text2: str,
        target1: str = "",
        target2: str = "",
        kw1: List[str] = None,
        kw2: List[str] = None,
    ) -> float:
        doc1 = {"content": text1, "target": target1, "keywords": kw1 or []}
        doc2 = {"content": text2, "target": target2, "keywords": kw2 or []}
        return self._facade.algorithm.calculate_similarity(doc1, doc2)

    def _create_merge_proposal(
        self,
        target_ids: List[str],
        topic: str,
        confidence: float = 0.90,
        target_mode: str = "knowledge_merge",
    ) -> Optional[str]:
        try:
            builder = (
                ProposalBuilder(self.memory).set_topic(topic).set_confidence(confidence)
            )
            for tid in target_ids:
                builder.add_target(tid)
            proposal = builder.build()
            return self._facade.transaction_manager.create_proposal(proposal)
        except Exception:
            return None

    def _get_active_merge_targets(self) -> List[str]:
        return self._facade.transaction_manager.get_active_targets()
