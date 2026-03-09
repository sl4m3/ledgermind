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
        """DEPRECATED: Use _keyword_semantic_similarity instead."""
        return 0.0

    def _keyword_semantic_similarity(self, doc1: Dict[str, Any], doc2: Dict[str, Any], memory: Optional[MemoryProtocol] = None) -> float:
        """Calculates semantic similarity between sets of keywords using embeddings."""
        kw1_set = self._get_doc_keywords_set(doc1)
        kw2_set = self._get_doc_keywords_set(doc2)

        if not kw1_set and not kw2_set:
            return 1.0
        if not kw1_set or not kw2_set:
            return 0.5 # Neutral penalty for missing keywords in one doc

        kw1 = sorted(list(kw1_set))
        kw2 = sorted(list(kw2_set))
        text1 = ", ".join(kw1)
        text2 = ", ".join(kw2)
        
        id1 = f"kw_{doc1.get('fid', hash(text1))}"
        id2 = f"kw_{doc2.get('fid', hash(text2))}"
        
        try:
            emb1 = self._get_cached_embedding(id1, text1)
            emb2 = self._get_cached_embedding(id2, text2)
            # Normal cosine similarity between keyword bags
            dot = np.dot(emb1, emb2)
            norm = np.linalg.norm(emb1) * np.linalg.norm(emb2)
            return float(dot / norm) if norm > 0 else 0.0
        except Exception:
            return 0.0

    def _target_similarity(self, doc1: Dict[str, Any], doc2: Dict[str, Any]) -> float:
        """Calculates Jaccard similarity between hierarchical target paths."""
        t1_raw = doc1.get('target', 'unknown') or 'unknown'
        t2_raw = doc2.get('target', 'unknown') or 'unknown'
        
        if t1_raw == t2_raw:
            return 1.0
            
        s1 = set(part for part in str(t1_raw).split('/') if part)
        s2 = set(part for part in str(t2_raw).split('/') if part)
        
        if not s1 or not s2:
            return 0.0
            
        intersection = s1.intersection(s2)
        union = s1.union(s2)
        
        jaccard = len(intersection) / len(union) if union else 0.0
        
        # Hard constraint: if root modules (first segment) differ, similarity is 0
        root1 = str(t1_raw).split('/')[0] if s1 else None
        root2 = str(t2_raw).split('/')[0] if s2 else None
        if root1 and root2 and root1 != root2:
            return 0.0
            
        return jaccard

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
        """
        Quadratic Scoring Model (V9.0).
        Maximizes the gap by squaring the base semantic score.
        Target similarity provides a small additive boost.
        """
        id1 = doc1.get('fid', doc1.get('id'))
        id2 = doc2.get('fid', doc2.get('id'))
        
        cache_key = None
        if self._cache_enabled and id1 and id2:
            cache_key = tuple(sorted([str(id1), str(id2)]))
            if cache_key in self._pairwise_cache:
                return self._pairwise_cache[cache_key]

        # 1. Component Calculation
        semantic_sim = self._semantic_similarity(doc1, doc2, memory)
        target_sim = self._target_similarity(doc1, doc2)
        kw_sim = self._keyword_semantic_similarity(doc1, doc2, memory)

        # 2. Base Semantic (80/20 mix)
        base_semantic = (0.80 * semantic_sim) + (0.20 * kw_sim)
        
        # 3. Quadratic Expansion + Target Boost
        # Squaring lowers mid-range values significantly, increasing the gap.
        # Target match adds a flat 0.05 bonus.
        combined = (base_semantic ** 2) + (0.05 * target_sim)

        # 4. Near-Identity Protection (Strict)
        if semantic_sim >= self.SEMANTIC_CASI_IDENTICAL:
            combined = max(combined, semantic_sim * 0.99)

        if self._cache_enabled and cache_key:
            self._pairwise_cache[cache_key] = combined

        logger.debug(f"Quadratic Cluster: sem={semantic_sim:.4f}, kw={kw_sim:.4f}, target={target_sim:.4f} -> combined={combined:.4f}")
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
