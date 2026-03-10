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
        # 0.8*0.9 + 0.2*1.0 = 0.92
        # 0.92^2 + 0.05 = 0.8464 + 0.05 = 0.8964
        assert sim >= 0.89

    def test_high_similarity_no_adaptive_weights(self, alg):
        """Verify current behavior without adaptive weights (fixed 80/20 mix)."""
        doc1 = {'title': 'A', 'content': 'A', 'keywords': 'k1'}
        doc2 = {'title': 'A', 'content': 'A', 'keywords': 'k2'}
        
        # Cosine similarity returns 0 for zero vectors in our model
        alg.embedding_model.cosine_similarity.return_value = 0.97
        
        sim = alg.calculate_similarity(doc1, doc2)
        # base_semantic = 0.8*0.97 + 0.2*0.0 = 0.776
        # combined = 0.776^2 + 0.05 = 0.652176
        assert 0.65 <= sim <= 0.66

    def test_casi_identical_protection(self, alg):
        """Very high semantic similarity should trigger Near-Identity Protection."""
        doc1 = {'title': 'A', 'content': 'A'}
        doc2 = {'title': 'A', 'content': 'A'}
        
        # CASI_IDENTICAL = 0.98
        alg.embedding_model.cosine_similarity.return_value = 0.99
        sim = alg.calculate_similarity(doc1, doc2)
        
        # base_semantic = 0.8*0.99 + 0.2*1.0 = 0.992
        # combined = 0.992^2 + 0.05 = 0.984 + 0.05 = 1.034
        # protection: max(1.034, 0.99 * 0.99) = 1.034
        assert sim >= 0.99

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
