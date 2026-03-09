import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Set
from ..types import MemoryProtocol

logger = logging.getLogger("ledgermind.core.merging.algorithms")

class DuplicateSearchAlgorithm(ABC):
    """
    Duplicate search strategy.
    Defines the interface for various search and similarity estimation algorithms.
    """

    @abstractmethod
    def search(self, candidate: Dict[str, Any], memory: MemoryProtocol) -> List[Dict[str, Any]]:
        """
        Performs a search for potential duplicates for the given candidate.
        
        Args:
            candidate: Dictionary with candidate document data.
            memory: Memory instance satisfying MemoryProtocol.
            
        Returns:
            List of found duplicates as dictionaries.
        """
        pass

    @abstractmethod
    def calculate_similarity(self, doc1: Dict[str, Any], doc2: Dict[str, Any]) -> float:
        """
        Calculates similarity metric between two documents.
        
        Args:
            doc1: First document.
            doc2: Second document.
            
        Returns:
            Value from 0.0 to 1.0, where 1.0 is full identity.
        """
        pass

class RRFJaccardAlgorithm(DuplicateSearchAlgorithm):
    """
    Search algorithm using Jaccard coefficient and (optionally) vector search.
    """

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def search(self, candidate: Dict[str, Any], memory: MemoryProtocol) -> List[Dict[str, Any]]:
        cand_id = candidate.get('fid', candidate.get('id', 'unknown'))
        logger.debug(f"RRFJaccard: Starting search for {cand_id}")
        results = []
        try:
            # First, try to use vector index for efficient pre-filtering
            all_docs = []
            query = f"{candidate.get('title', '')} {candidate.get('content', '')}".strip()
            
            if query and hasattr(memory, 'vector_index') and hasattr(memory.vector_index, 'search'):
                logger.debug("Using vector index for pre-filtering...")
                # Assume search returns a list of dictionaries or objects with metadata
                search_results = memory.vector_index.search(query, limit=50)
                # Extract dictionaries if objects were returned
                all_docs = [doc if isinstance(doc, dict) else getattr(doc, 'metadata', doc) for doc in search_results]
            else:
                logger.debug("Vector index unavailable, falling back to list_all()...")
                all_docs = memory.semantic.meta.list_all()

            for doc_data in all_docs:
                doc_id = doc_data.get('fid', doc_data.get('id', 'unknown'))
                if doc_id == cand_id:
                    continue
                
                sim = self.calculate_similarity(candidate, doc_data)
                if sim >= self.threshold:
                    logger.debug(f"Match found: {doc_id} (Similarity: {sim:.2f})")
                    results.append(doc_data)
            return results
        except Exception as e:
            logger.error(f"Error during duplicate search: {e}")
            return []

    def calculate_similarity(self, doc1: Dict[str, Any], doc2: Dict[str, Any]) -> float:
        """Jaccard coefficient calculation (Intersection over Union)."""
        def get_tokens(doc: Dict[str, Any]) -> Set[str]:
            import re
            text = f"{doc.get('title', '')} {doc.get('content', '')}".lower()
            # Split by any non-word character to get cleaner tokens
            tokens = set(re.findall(r'\w+', text))
            
            # Handle keywords (could be string or list)
            kw = doc.get('keywords', [])
            if isinstance(kw, str):
                # Handle comma-separated string
                kw_tokens = [k.strip().lower() for k in kw.split(',') if k.strip()]
                tokens.update(kw_tokens)
            elif isinstance(kw, list):
                tokens.update([str(k).lower() for k in kw])
                
            return tokens

        tokens1 = get_tokens(doc1)
        tokens2 = get_tokens(doc2)

        if not tokens1 and not tokens2:
            return 0.0

        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        
        similarity = len(intersection) / len(union) if union else 0.0
        logger.debug(f"Jaccard similarity: {similarity:.4f}")
        return similarity

import math
from collections import Counter

class BM25Algorithm(DuplicateSearchAlgorithm):
    """
    Search algorithm based on a simplified BM25 scoring model.
    """
    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self.k1 = 1.5
        self.b = 0.75

    def search(self, candidate: Dict[str, Any], memory: MemoryProtocol) -> List[Dict[str, Any]]:
        logger.debug(f"BM25: Starting search for {candidate.get('id', 'unknown')}")
        results = []
        try:
            # We fetch all docs to compute average document length (required for BM25)
            all_docs = memory.semantic.meta.list_all()
            if not all_docs:
                return []
                
            # Filter out the candidate itself
            corpus = [d for d in all_docs if d.get('id') != candidate.get('id') and d.get('fid') != candidate.get('fid')]
            if not corpus:
                return []

            candidate_tokens = self._tokenize(candidate)
            if not candidate_tokens:
                return []

            # Precompute document lengths and average length
            doc_lengths = {d.get('id', d.get('fid', str(i))): len(self._tokenize(d)) for i, d in enumerate(corpus)}
            avgdl = sum(doc_lengths.values()) / len(doc_lengths) if doc_lengths else 1.0

            # Precompute Document Frequencies (DF)
            df = Counter()
            for doc in corpus:
                tokens = set(self._tokenize(doc))
                df.update(tokens)
            
            N = len(corpus)

            for doc in corpus:
                doc_id = doc.get('id', doc.get('fid', 'unknown'))
                doc_tokens = self._tokenize(doc)
                if not doc_tokens:
                    continue
                    
                tf = Counter(doc_tokens)
                doc_len = doc_lengths.get(doc_id, len(doc_tokens))
                
                score = 0.0
                for token in candidate_tokens:
                    if token in tf:
                        # IDF calculation
                        n_q = df.get(token, 0)
                        idf = math.log(((N - n_q + 0.5) / (n_q + 0.5)) + 1.0)
                        
                        # TF calculation
                        freq = tf[token]
                        numerator = freq * (self.k1 + 1)
                        denominator = freq + self.k1 * (1 - self.b + self.b * (doc_len / avgdl))
                        
                        score += idf * (numerator / denominator)
                
                # Normalize score loosely to 0-1 for threshold comparison
                # BM25 isn't naturally 0-1, so we use a heuristic max normalization
                # A heuristic approach: max possible score for a single term is roughly idf * (k1+1).
                # We can normalize by candidate length * max term score, or just use raw score with a tuned threshold.
                # To maintain compatibility with threshold (0-1), we do a simple sigmoid or max bounding:
                normalized_score = 1.0 - math.exp(-0.1 * score) 

                if normalized_score >= self.threshold:
                    logger.debug(f"BM25 Match found: {doc_id} (Score: {normalized_score:.2f})")
                    results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error during BM25 search: {e}")
            return []

    def calculate_similarity(self, doc1: Dict[str, Any], doc2: Dict[str, Any]) -> float:
        """Fallback simple similarity if used outside full corpus search."""
        tokens1 = set(self._tokenize(doc1))
        tokens2 = set(self._tokenize(doc2))
        if not tokens1 or not tokens2:
            return 0.0
        return len(tokens1.intersection(tokens2)) / len(tokens1.union(tokens2))

    def _tokenize(self, doc: Dict[str, Any]) -> List[str]:
        text = f"{doc.get('title', '')} {doc.get('content', '')}".lower()
        tokens = text.split()
        if isinstance(doc.get('keywords'), list):
            tokens.extend([k.lower() for k in doc['keywords']])
        return tokens

from .vector_similarity import VectorEmbeddingAlgorithm

__all__ = [
    'DuplicateSearchAlgorithm',
    'RRFJaccardAlgorithm',
    'BM25Algorithm',
    'VectorEmbeddingAlgorithm'
]
