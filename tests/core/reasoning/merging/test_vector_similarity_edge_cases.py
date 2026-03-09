import pytest
import numpy as np
from unittest.mock import MagicMock
from ledgermind.core.reasoning.merging.algorithms.vector_similarity import VectorEmbeddingAlgorithm

class TestVectorSimilarityEdgeCases:

    @pytest.fixture
    def alg(self):
        # Mocking embedding model to avoid real Jina loading
        mock_model = MagicMock()
        # Cosine similarity 1.0 mock
        mock_model.cosine_similarity.return_value = 1.0
        # Return zeros for any text
        mock_model.encode.return_value = np.zeros((2, 768))
        
        return VectorEmbeddingAlgorithm(
            threshold=0.75, 
            embedding_model=mock_model,
            use_adaptive_weights=True
        )

    def test_no_keywords_no_penalty(self, alg):
        """If both docs have no keywords, similarity should be high (semantic only)."""
        doc1 = {'title': 'A', 'content': 'A', 'keywords': ''}
        doc2 = {'title': 'A', 'content': 'A', 'keywords': []}
        
        # Manually force semantic similarity to high value
        alg.embedding_model.cosine_similarity.return_value = 0.9
        
        sim = alg.calculate_similarity(doc1, doc2)
        # Should be exactly 0.9 because effective_kw_weight * 1.0 matches semantic
        # Or if adaptive weight dampens kw influence
        assert sim >= 0.9

    def test_adaptive_weight_high_similarity(self, alg):
        """Near identical semantic similarity should dampen keyword influence."""
        doc1 = {'title': 'A', 'content': 'A', 'keywords': 'k1'}
        doc2 = {'title': 'A', 'content': 'A', 'keywords': 'k2'}
        
        # 0.97 is > 0.95 (NEAR_IDENTICAL), weight becomes 0.15 * 0.1 = 0.015
        alg.embedding_model.cosine_similarity.return_value = 0.97
        
        sim = alg.calculate_similarity(doc1, doc2)
        # combined = 0.985 * 0.97 + 0.015 * 0.0 = 0.95545
        assert sim > 0.95

    def test_casi_identical_boost(self, alg):
        """Very high semantic similarity should get a boost."""
        doc1 = {'title': 'A', 'content': 'A'}
        doc2 = {'title': 'A', 'content': 'A'}
        
        alg.embedding_model.cosine_similarity.return_value = 0.99
        sim = alg.calculate_similarity(doc1, doc2)
        
        # 0.99 * 0.99 = 0.9801 (even if keywords mismatch)
        assert sim >= 0.98

    def test_near_identical_string_optimization(self, alg):
        """The search method should use _is_near_identical fast-path."""
        candidate = {'title': 'Exact Title Match', 'content': 'Same content'}
        all_docs = [{'fid': 'd1', 'title': 'Exact Title Match', 'content': 'Same content'}]
        
        class MockMemory:
            class MockSemantic:
                class MockMeta:
                    def list_all(self): return all_docs
                meta = MockMeta()
            semantic = MockSemantic()
            vector = None

        # Even if model is broken, near-identical should work
        alg.embedding_model.encode.side_effect = Exception("Should not be called")
        
        results = alg.search(candidate, MockMemory())
        assert len(results) == 1
        assert results[0]['fid'] == 'd1'
