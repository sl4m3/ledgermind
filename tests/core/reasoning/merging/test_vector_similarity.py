import pytest
import numpy as np
from ledgermind.core.reasoning.merging.algorithms.vector_similarity import VectorEmbeddingAlgorithm

class TestVectorEmbeddingAlgorithm:

    @pytest.fixture
    def alg(self):
        return VectorEmbeddingAlgorithm(threshold=0.8, enable_cache=True)

    def test_identical_docs(self, alg):
        """Идентичные документы => similarity 1.0."""
        doc = {'fid': '1', 'title': 'T', 'content': 'C', 'keywords': ['k']}
        sim = alg.calculate_similarity(doc, doc.copy())
        assert sim >= 0.99

    def test_completely_different(self, alg):
        """Разные документы => similarity низкий."""
        doc1 = {'title': 'A', 'content': 'A'}
        doc2 = {'title': 'B', 'content': 'B'}
        sim = alg.calculate_similarity(doc1, doc2)
        assert sim < 0.3

    def test_keyword_boost(self, alg):
        """Общие keywords повышают similarity."""
        doc1 = {'title': 'A', 'content': 'A', 'keywords': ['shared', 'k1']}
        doc2 = {'title': 'B', 'content': 'B', 'keywords': ['shared', 'k2']}

        sim_with = alg.calculate_similarity(doc1, doc2)

        doc1_nk = {k: v for k, v in doc1.items() if k != 'keywords'}
        doc2_nk = {k: v for k, v in doc2.items() if k != 'keywords'}
        sim_without = alg.calculate_similarity(doc1_nk, doc2_nk)

        assert sim_with > sim_without

    def test_cache_functionality(self, alg):
        """Кэш возвращает одинаковые значения."""
        doc1 = {'title': 'T', 'content': 'Content', 'fid': '1'}
        doc2 = {'title': 'S', 'content': 'Second', 'fid': '2'}

        sim1 = alg.calculate_similarity(doc1, doc2)
        sim2 = alg.calculate_similarity(doc1, doc2)

        assert sim1 == sim2
        assert ('1', '2') in alg._pairwise_cache or ('1', '2') in alg._pairwise_cache

    def test_threshold_filtering(self, alg):
        """Search возвращает только выше порога."""
        candidate = {
            'fid': 'cand',
            'title': 'Machine Learning',
            'content': 'Neural networks',
            'keywords': ['ML']
        }

        all_docs = [
            {'fid': 'd1', 'title': 'ML basics', 'content': 'Neural nets intro', 'keywords': ['ML']},  # высокая
            {'fid': 'd2', 'title': 'Cooking', 'content': 'Recipes', 'keywords': ['food']},  # низкая
        ]

        class MockMemory:
            class MockSemantic:
                class MockMeta:
                    def list_all(self):
                        return all_docs
                meta = MockMeta()
            semantic = MockSemantic()
            vector_index = None

        results = alg.search(candidate, MockMemory())
        assert len(results) == 1
        assert results[0]['fid'] == 'd1'
