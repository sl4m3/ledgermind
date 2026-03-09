import logging
from typing import List, Dict, Any, Tuple, Optional, Set
import numpy as np
import time
from difflib import SequenceMatcher

from . import DuplicateSearchAlgorithm
from ..embedding_model import JinaEmbeddingModel
from ..types import MemoryProtocol

logger = logging.getLogger("ledgermind.core.merging.vector")

class VectorEmbeddingAlgorithm(DuplicateSearchAlgorithm):
    """
    ML-algorithm based on semantic embeddings with adaptive weighting.
    """

    # Adaptive thresholds for keyword weight dampening
    SEMANTIC_NEAR_IDENTICAL = 0.95
    SEMANTIC_HIGH_SIMILARITY = 0.85
    SEMANTIC_CASI_IDENTICAL = 0.98

    def __init__(
        self,
        threshold: float = 0.75,
        embedding_model: Optional[JinaEmbeddingModel] = None,
        keyword_weight: float = 0.15,
        use_vector_search: bool = True,
        vector_search_limit: int = 100,
        enable_cache: bool = True,
        use_adaptive_weights: bool = True
    ):
        self.threshold = threshold
        self.keyword_weight = max(0.0, min(1.0, keyword_weight))
        self.use_vector_search = use_vector_search
        self.vector_search_limit = vector_search_limit
        self._cache_enabled = enable_cache
        self.use_adaptive_weights = use_adaptive_weights
        
        self._pairwise_cache: Dict[Tuple[str, str], float] = {}
        self._embedding_memory_cache: Dict[str, np.ndarray] = {}
        
        self.embedding_model = embedding_model

    def _ensure_model(self, memory: Optional[MemoryProtocol] = None):
        """Ensures the embedding model is initialized, potentially reusing from memory."""
        if self.embedding_model is not None:
            return

        model_instance = None
        if memory and hasattr(memory, 'vector') and memory.vector is not None:
            try:
                model_instance = memory.vector.model
                logger.info("Reusing existing embedding model from VectorStore.")
            except Exception as e:
                logger.debug(f"Could not borrow model from VectorStore: {e}")

        self.embedding_model = JinaEmbeddingModel(model_instance=model_instance)

    def _get_doc_text(self, doc: Dict[str, Any]) -> str:
        """Standardized text extraction matching indexing format (title\\ncontent)."""
        title = doc.get('title', '').strip()
        # 'content' field in search results often maps to 'rationale' during recording
        content = doc.get('content', doc.get('rationale', '')).strip()
        
        # Consistent format: "Title\nRationale/Content"
        return f"{title}\n{content}".strip()

    def _get_doc_keywords_set(self, doc: Dict[str, Any]) -> Set[str]:
        """Normalized keywords set."""
        keywords = doc.get('keywords', [])
        if isinstance(keywords, str):
            import re
            keywords = [k.strip() for k in re.split(r'[,\s]+', keywords) if k.strip()]
        elif not isinstance(keywords, list):
            keywords = []
        return set(str(k).lower().strip() for k in keywords if k)

    def _keyword_similarity(self, doc1: Dict[str, Any], doc2: Dict[str, Any]) -> float:
        """Jaccard similarity for keywords with 'no-penalty' rule."""
        kw1 = self._get_doc_keywords_set(doc1)
        kw2 = self._get_doc_keywords_set(doc2)

        # If both have no keywords, it's not a mismatch
        if not kw1 and not kw2:
            return 1.0

        intersection = kw1.intersection(kw2)
        union = kw1.union(kw2)
        return len(intersection) / len(union) if union else 0.0

    def _get_cached_embedding(self, doc_id: str, text: str) -> np.ndarray:
        """Retrieve or compute embedding with per-document and text-hash caching."""
        # 1. Primary memory cache check (extremely fast, avoids all processing)
        if doc_id and doc_id in self._embedding_memory_cache:
            return self._embedding_memory_cache[doc_id]
        
        # 2. Compute embedding (will use model's internal hash-based LRU cache)
        try:
            start = time.time()
            embedding = self.embedding_model.encode([text])[0]
            elapsed = (time.time() - start) * 1000
            
            logger.debug(f"Computed embedding for {doc_id} in {elapsed:.2f}ms")
            
            # Save to local session cache
            if doc_id:
                self._embedding_memory_cache[doc_id] = embedding
            return embedding
        except Exception as e:
            logger.error(f"Failed to encode text for {doc_id}: {e}")
            return np.zeros(1024) # Fallback dimension for Jina v5

    def _semantic_similarity(self, doc1: Dict[str, Any], doc2: Dict[str, Any], memory: Optional[MemoryProtocol] = None) -> float:
        """Semantic similarity through embeddings with optimized caching."""
        self._ensure_model(memory)
        text1 = self._get_doc_text(doc1)
        text2 = self._get_doc_text(doc2)

        if not text1.strip() or not text2.strip():
            return 0.0

        id1 = doc1.get('fid', doc1.get('id'))
        id2 = doc2.get('fid', doc2.get('id'))

        try:
            emb1 = self._get_cached_embedding(id1, text1)
            emb2 = self._get_cached_embedding(id2, text2)
            
            # Use model's similarity method (handles normalization)
            return self.embedding_model.cosine_similarity(emb1, emb2)
        except Exception as e:
            logger.error(f"Semantic similarity error: {e}")
            return 0.0

    def calculate_similarity(self, doc1: Dict[str, Any], doc2: Dict[str, Any], memory: Optional[MemoryProtocol] = None) -> float:
        """Combined score with adaptive weighting."""
        id1 = doc1.get('fid', doc1.get('id'))
        id2 = doc2.get('fid', doc2.get('id'))
        
        cache_key = None
        if self._cache_enabled and id1 and id2:
            cache_key = tuple(sorted([str(id1), str(id2)]))
            if cache_key in self._pairwise_cache:
                return self._pairwise_cache[cache_key]

        semantic_sim = self._semantic_similarity(doc1, doc2, memory)
        keyword_sim = self._keyword_similarity(doc1, doc2)

        # Adaptive keyword influence
        effective_kw_weight = self.keyword_weight
        if self.use_adaptive_weights:
            if semantic_sim >= self.SEMANTIC_NEAR_IDENTICAL:
                effective_kw_weight *= 0.1 # Ignore keywords for near-duplicates
            elif semantic_sim >= self.SEMANTIC_HIGH_SIMILARITY:
                effective_kw_weight *= 0.5 # Reduce keyword penalty

        combined = (1.0 - effective_kw_weight) * semantic_sim + effective_kw_weight * keyword_sim

        # Casi-identical boost
        if semantic_sim >= self.SEMANTIC_CASI_IDENTICAL:
            combined = max(combined, semantic_sim * 0.99)

        if self._cache_enabled and cache_key:
            self._pairwise_cache[cache_key] = combined

        logger.debug(f"Similarity: sem={semantic_sim:.4f}, kw={keyword_sim:.4f}, combined={combined:.4f} (kw_weight={effective_kw_weight:.3f})")
        return float(combined)

    def search(self, candidate: Dict[str, Any], memory: Any) -> List[Dict[str, Any]]:
        """Optimized search with integrated QueryService metadata enrichment."""
        start = time.time()
        cand_id = candidate.get('fid', candidate.get('id', 'unknown'))
        logger.info(f"VectorEmbedding: searching duplicates for {cand_id}")

        try:
            query = self._get_doc_text(candidate)
            if not query.strip():
                all_docs = memory.semantic.meta.list_all()
            elif hasattr(memory, 'search_decisions'):
                # Use unified search service to get enriched documents
                # mode="maintenance" includes drafts and active decisions
                all_docs = memory.search_decisions(query, limit=self.vector_search_limit, mode="maintenance")
            elif hasattr(memory, '_query') and hasattr(memory._query, 'search'):
                all_docs = memory._query.search(query, limit=self.vector_search_limit, mode="maintenance")
            else:
                # Fallback if no service is available
                all_docs = memory.semantic.meta.list_all()
        except Exception as e:
            logger.error(f"Search retrieval error: {e}")
            return []

        results = []
        candidate_text = self._get_doc_text(candidate)

        for doc_data in all_docs:
            doc_id = doc_data.get('fid', doc_data.get('id', 'unknown'))
            if doc_id == cand_id:
                continue

            # Fast path: near-identical strings
            doc_text = self._get_doc_text(doc_data)
            if not doc_text.strip():
                # Skip documents with no content to avoid false 0.0 similarity
                continue

            if self._is_near_identical(candidate_text, doc_text):
                results.append(doc_data)
                continue

            # Stage 2: Precise similarity calculation
            sim = self.calculate_similarity(candidate, doc_data, memory=memory)
            if sim >= self.threshold:
                results.append(doc_data)

        elapsed = time.time() - start
        logger.info(f"Search complete in {elapsed:.3f}s, found {len(results)} duplicates")
        return results

    def _is_near_identical(self, text1: str, text2: str, threshold: float = 0.95) -> bool:
        """Fast identity check using SequenceMatcher."""
        if text1 == text2: return True
        if not text1 or not text2: return False
        
        # Quick length check
        len1, len2 = len(text1), len(text2)
        if abs(len1 - len2) / max(len1, len2) > (1.0 - threshold):
            return False
            
        if len1 > 100 and len2 > 100:
            if text1 in text2 or text2 in text1: return True
            
        return SequenceMatcher(None, text1[:500], text2[:500]).ratio() > threshold

    def clear_cache(self):
        """Clears all internal caches."""
        self._pairwise_cache.clear()
        self._embedding_memory_cache.clear()
        if self.embedding_model:
            self.embedding_model.cache._cache.clear()
