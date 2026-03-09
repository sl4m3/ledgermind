from typing import List, Dict, Any, Optional
import logging
import functools
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
        alg_name = alg_config.get("name", "rrf_jaccard")
        threshold = self.config.get_algorithm_config(alg_name).get("threshold", self.config.threshold)
        
        self.algorithm = AlgorithmFactory.create(alg_name, threshold=0.65) # Lower threshold for grey zone
        from .llm_validator import MergingLLMValidator
        self.llm_validator = MergingLLMValidator(memory)

    def scan_for_duplicates(self, candidates: List[Dict[str, Any]], threshold: Optional[float] = None) -> Result:
        """
        High-performance clustered scan focusing on stable (completed) and active truths.
        Implements Stage 1 (Clustering) and Stage 3 (Pruning/Truth Resolution) of the plan.
        """
        MERGE_THRESHOLD = 0.85
        VALIDATION_THRESHOLD = 0.65
        
        logger.info(f"Starting clustered scan. Initial candidates: {len(candidates)}")
        
        # 1. PRE-PROCESSING: Local metadata cache of 'True' and 'Completed' versions
        resolved_candidates = []
        meta_cache = {}
        
        # Load all metadata once to avoid DB hits in the loop
        all_metadata = self.memory.semantic.meta.list_all()
        # Build a fast lookup map
        full_meta_map = {m.get('fid', m.get('id')): m for m in all_metadata if m}

        for cand in candidates:
            cand_id = cand.get('fid', cand.get('id'))
            
            # Resolve to the latest version using internal QueryService logic
            resolved = self.memory._resolve_to_truth(cand_id, mode="balanced", cache=full_meta_map)
            if not resolved:
                continue
                
            # FILTER: Only stable knowledge (Stage 3)
            if resolved.get('status') in ('superseded', 'deprecated', 'rejected', 'falsified'):
                continue
            
            # FILTER: Must be enriched to have reliable semantic data
            if resolved.get('enrichment_status') != 'completed':
                continue

            fid = resolved.get('fid')
            if fid not in meta_cache:
                meta_cache[fid] = resolved
                resolved_candidates.append(resolved)

        logger.info(f"Filtered to {len(resolved_candidates)} stable active truths for clustering.")
        
        # 2. PRE-CACHE EMBEDDINGS (Batch optimization)
        # We must ensure the model is initialized before batch encoding
        if hasattr(self.algorithm, '_ensure_model'):
            self.algorithm._ensure_model(self.memory)

        if hasattr(self.algorithm, 'embedding_model') and self.algorithm.embedding_model:
            logger.info(f"Pre-caching embeddings for {len(resolved_candidates)} candidates...")
            all_texts = [self.algorithm._get_doc_text(c) for c in resolved_candidates]
            try:
                # Batch encode all texts (O(N) instead of O(N^2))
                embeddings = self.algorithm.embedding_model.encode(all_texts)
                for cand, emb in zip(resolved_candidates, embeddings):
                    fid = cand.get('fid', cand.get('id'))
                    if fid:
                        self.algorithm._embedding_memory_cache[fid] = emb
                logger.info(f"Successfully pre-cached {len(embeddings)} embeddings.")
            except Exception as e:
                logger.warning(f"Batch pre-caching failed: {e}. Falling back to on-demand caching.")

        proposals = []
        handled_fids = set()
        
        # Use thresholds from config if available, otherwise fall back to defaults
        merge_threshold = threshold or self.config.threshold or 0.85
        validation_threshold = self.config.get_algorithm_config("default").get("validation_threshold", 0.65)

        try:
            for i, candidate in enumerate(resolved_candidates):
                cand_id = candidate.get('fid')
                if cand_id in handled_fids:
                    continue
                
                query_text = self.algorithm._get_doc_text(candidate)
                if not query_text.strip(): continue

                # 3. FAST SEARCH: Use vector index (Stage 1 search)
                search_results = self.memory.vector.search(query_text, limit=30)
                if not search_results:
                    continue

                to_merge = []
                to_validate = []

                for res in search_results:
                    doc_id = res.get('id')
                    if doc_id == cand_id or doc_id in handled_fids: 
                        continue
                    
                    # Resolve found document to its truth
                    target_doc = self.memory._resolve_to_truth(doc_id, mode="balanced", cache=full_meta_map)
                    # ALLOW: 'active' AND 'draft' for merging (Stage 1 consolidation)
                    if not target_doc or target_doc.get('status') not in ('active', 'draft'):
                        continue
                        
                    if target_doc.get('enrichment_status') != 'completed':
                        continue

                    # 4. FAST COMPARISON (Will use pre-cached embeddings)
                    sim_score = self.algorithm.calculate_similarity(candidate, target_doc, memory=self.memory)
                    
                    if sim_score >= merge_threshold:
                        to_merge.append(target_doc)
                    elif sim_score >= validation_threshold:
                        to_validate.append(target_doc)

                # STAGE 1: Aggregated Clustering
                # Create ONE proposal for high-confidence merges
                if to_merge:
                    handled_fids.add(cand_id)
                    for d in to_merge: handled_fids.add(d['fid'])
                    
                    topic = f"Merge Cluster: {candidate.get('topic', candidate.get('title', 'Knowledge Group'))}"
                    # Confidence for merges is high, use knowledge_merge target
                    pid = self.create_merge_proposal([candidate] + to_merge, topic=topic, target="knowledge_merge")
                    if pid: proposals.append(pid)
                
                # Create ONE proposal for grey-zone validation
                # Note: We only create validation cluster if candidate wasn't already merged
                elif to_validate:
                    handled_fids.add(cand_id)
                    # We don't mark validation targets as 'handled' to let them 
                    # potentially join stronger merge clusters later
                    
                    topic = f"Validation Cluster: Potential Duplicates"
                    pid = self.create_merge_proposal([candidate] + to_validate, topic=topic, target="knowledge_validation")
                    if pid: proposals.append(pid)

            return Result(success=True, data=proposals)
        except Exception as e:
            logger.error(f"Critical error during scan: {e}", exc_info=True)
            return Result(success=False, error=str(e))

    def create_merge_proposal(self, group: List[Dict[str, Any]], topic: Optional[str] = None, confidence: Optional[float] = None, target: str = "knowledge_merge") -> Optional[str]:
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
                sim_scores = [self.algorithm.calculate_similarity(base_doc, doc) for doc in group[1:]]
                avg_confidence = sum(sim_scores) / len(sim_scores) if sim_scores else 0.0
                builder.set_confidence(avg_confidence)
            
            for doc in group:
                builder.add_target(doc.get('id', doc.get('fid', 'unknown_id')))
                
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

    def _calculate_jaccard(self, text1: str, text2: str, target1: str = "", target2: str = "", kw1: List[str] = None, kw2: List[str] = None) -> float:
        doc1 = {"content": text1, "target": target1, "keywords": kw1 or []}
        doc2 = {"content": text2, "target": target2, "keywords": kw2 or []}
        return self._facade.algorithm.calculate_similarity(doc1, doc2)

    def _create_merge_proposal(self, target_ids: List[str], topic: str, confidence: float = 0.90, target_mode: str = "knowledge_merge") -> Optional[str]:
        try:
            builder = ProposalBuilder(self.memory).set_topic(topic).set_confidence(confidence)
            for tid in target_ids:
                builder.add_target(tid)
            proposal = builder.build()
            return self._facade.transaction_manager.create_proposal(proposal)
        except Exception:
            return None

    def _get_active_merge_targets(self) -> List[str]:
        return self._facade.transaction_manager.get_active_targets()
